"""GitHub connector: fetches an issue via `gh` CLI and walks its references."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from gg.tasks.connectors._refs import extract_mentions, extract_refs, extract_urls
from gg.tasks.connectors.base import FetchOptions, Ref, TaskConnector
from gg.tasks.schema.raw import Artifact, ArtifactKind, RawTaskBundle

GH_FULL_REF_RE = re.compile(r"^([A-Za-z0-9._-]+/[A-Za-z0-9._-]+)#(\d+)$")
GH_SHORT_REF_RE = re.compile(r"^#(\d+)$")
ISSUE_URL_RE = re.compile(
    r"^https?://github\.com/([A-Za-z0-9._-]+/[A-Za-z0-9._-]+)/(?:issues|pull)/(\d+)",
)
ISSUE_URL_INLINE_RE = re.compile(
    r"https?://github\.com/([A-Za-z0-9._-]+/[A-Za-z0-9._-]+)/(?:issues|pull)/(\d+)",
)

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp")
DESIGN_HOSTS = ("figma.com", "pixso.net", "pixso.cn", "miro.com", "whimsical.com")


class GitHubCLIError(RuntimeError):
    pass


@dataclass
class _IssueView:
    """Raw JSON shape returned by `gh issue view --json ...`."""
    data: dict[str, Any]

    @property
    def number(self) -> int:
        return int(self.data.get("number", 0))

    @property
    def title(self) -> str:
        return self.data.get("title", "") or ""

    @property
    def body(self) -> str:
        return self.data.get("body", "") or ""

    @property
    def url(self) -> str:
        return self.data.get("url", "") or ""

    @property
    def state(self) -> str:
        return (self.data.get("state") or "open").lower()

    @property
    def author(self) -> str:
        a = self.data.get("author") or {}
        return a.get("login", "") if isinstance(a, dict) else ""

    @property
    def labels(self) -> list[str]:
        return [la.get("name", "") for la in self.data.get("labels", []) if la.get("name")]

    @property
    def assignees(self) -> list[str]:
        return [a.get("login", "") for a in self.data.get("assignees", []) if a.get("login")]

    @property
    def created_at(self) -> str:
        return self.data.get("createdAt", "") or ""

    @property
    def updated_at(self) -> str:
        return self.data.get("updatedAt", "") or ""

    @property
    def comments(self) -> list[dict[str, Any]]:
        return self.data.get("comments", []) or []


class GitHubConnector(TaskConnector):
    platform = "github"

    _ISSUE_FIELDS = (
        "number,title,body,url,state,labels,assignees,author,"
        "createdAt,updatedAt,comments"
    )

    def __init__(self, cwd: str = ".") -> None:
        self._cwd = cwd

    # -- ref handling --

    @classmethod
    def can_handle(cls, ref: str) -> bool:
        ref = ref.strip()
        return bool(GH_FULL_REF_RE.match(ref) or ISSUE_URL_RE.match(ref))

    @classmethod
    def parse_ref(cls, ref: str) -> Ref:
        ref = ref.strip()
        m = GH_FULL_REF_RE.match(ref)
        if m:
            repo, num = m.group(1), m.group(2)
            return Ref(platform=cls.platform, raw=ref, normalized=f"{repo}#{num}",
                       project=repo, external_id=num)
        m = ISSUE_URL_RE.match(ref)
        if m:
            repo, num = m.group(1), m.group(2)
            return Ref(platform=cls.platform, raw=ref, normalized=f"{repo}#{num}",
                       project=repo, external_id=num)
        m = GH_SHORT_REF_RE.match(ref)
        if m:
            return Ref(platform=cls.platform, raw=ref, normalized=f"#{m.group(1)}",
                       project="", external_id=m.group(1))
        raise ValueError(f"Not a GitHub ref: {ref!r} (expected owner/repo#N or URL)")

    def is_available(self) -> bool:
        return shutil.which("gh") is not None

    # -- fetching --

    def fetch(self, ref: Ref, options: FetchOptions) -> RawTaskBundle:
        if not ref.project:
            raise ValueError(
                f"GitHubConnector needs a full ref (owner/repo#N), got {ref.raw!r}",
            )

        visited: set[str] = set()
        root_artifact, extras = self._fetch_one(ref, options, depth=0, visited=visited)

        return RawTaskBundle(
            platform=self.platform,
            source_ref=ref.normalized,
            fetched_at=datetime.now(timezone.utc),
            root=root_artifact,
            artifacts=extras,
            max_depth=options.max_depth,
            visited_refs=sorted(visited),
        )

    def _fetch_one(
        self,
        ref: Ref,
        options: FetchOptions,
        *,
        depth: int,
        visited: set[str],
    ) -> tuple[Artifact, list[Artifact]]:
        """Fetch a single issue as an Artifact (kind=LINKED_TASK). Returns (root, siblings)."""
        visited.add(ref.normalized)

        raw = self._gh_issue_view(ref)
        view = _IssueView(raw)

        extras: list[Artifact] = []

        if options.include_comments and depth == 0:
            extras.extend(self._comments_to_artifacts(view.comments))

        body_text = view.body
        attachments = self._attachments_from_body(body_text)
        extras.extend(attachments)

        external = self._external_refs_from_body(body_text)
        extras.extend(external)

        mentions = self._mentions_to_artifacts(body_text)
        extras.extend(mentions)

        linked_children: list[Artifact] = []
        if options.include_linked and depth < options.max_depth:
            sources = [body_text]
            if options.include_comments and depth == 0:
                sources.extend(c.get("body", "") or "" for c in view.comments)
            linked_refs = self._collect_linked_refs(sources, default_repo=ref.project)
            for linked_ref in linked_refs:
                try:
                    parsed = self.parse_ref(linked_ref)
                except ValueError:
                    continue
                if not parsed.project:
                    continue
                if parsed.normalized in visited:
                    continue
                child_artifact, child_extras = self._fetch_one(
                    parsed, options, depth=depth + 1, visited=visited,
                )
                for ex in child_extras:
                    child_artifact.children.append(ex)
                linked_children.append(child_artifact)

        root = Artifact(
            kind=ArtifactKind.LINKED_TASK,
            title=view.title,
            url=view.url,
            content=body_text,
            metadata={
                "number": view.number,
                "state": view.state,
                "labels": view.labels,
                "assignees": view.assignees,
                "author": view.author,
                "created_at": view.created_at,
                "updated_at": view.updated_at,
                "platform": self.platform,
                "repo": ref.project,
                "depth": depth,
            },
            children=linked_children,
        )
        return root, extras

    # -- helpers --

    def _gh_issue_view(self, ref: Ref) -> dict[str, Any]:
        args = [
            "gh", "issue", "view", ref.external_id,
            "--repo", ref.project,
            "--json", self._ISSUE_FIELDS,
        ]
        try:
            result = subprocess.run(
                args, capture_output=True, text=True, timeout=30, cwd=self._cwd,
            )
        except FileNotFoundError as e:
            raise GitHubCLIError("gh CLI not found. Install it and run `gh auth login`.") from e

        if result.returncode != 0:
            raise GitHubCLIError(
                f"gh issue view {ref.project}#{ref.external_id} failed: "
                f"{result.stderr.strip() or 'unknown error'}",
            )
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as e:
            raise GitHubCLIError(f"gh returned invalid JSON: {e}") from e

    def _comments_to_artifacts(self, comments: list[dict[str, Any]]) -> list[Artifact]:
        out: list[Artifact] = []
        for c in comments:
            author = (c.get("author") or {}).get("login", "") if isinstance(c.get("author"), dict) else ""
            out.append(Artifact(
                kind=ArtifactKind.COMMENT,
                title=author or "anonymous",
                content=c.get("body", "") or "",
                metadata={
                    "author": author,
                    "created_at": c.get("createdAt", ""),
                    "updated_at": c.get("updatedAt", ""),
                },
            ))
        return out

    def _collect_linked_refs(self, texts: list[str], *, default_repo: str) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []

        def _push(ref: str) -> None:
            if ref not in seen:
                seen.add(ref)
                out.append(ref)

        for text in texts:
            if not text:
                continue
            for r in extract_refs(text, default_repo=default_repo):
                if r.platform != "github":
                    continue
                normalized = f"{default_repo}{r.normalized}" if r.normalized.startswith("#") else r.normalized
                _push(normalized)
            for m in ISSUE_URL_INLINE_RE.finditer(text):
                _push(f"{m.group(1)}#{m.group(2)}")

        return out

    def _attachments_from_body(self, body: str) -> list[Artifact]:
        out: list[Artifact] = []
        for url in extract_urls(body):
            lower = url.lower()
            if lower.startswith("https://github.com/") and (
                "/issues/" in lower or "/pull/" in lower
            ):
                continue
            if any(lower.endswith(ext) or f"{ext}?" in lower for ext in IMAGE_EXTS):
                out.append(Artifact(kind=ArtifactKind.IMAGE, url=url, title=url.rsplit("/", 1)[-1]))
                continue
            if "user-images.githubusercontent.com" in lower or "github.com/user-attachments/" in lower:
                out.append(Artifact(kind=ArtifactKind.ATTACHMENT, url=url,
                                    title=url.rsplit("/", 1)[-1]))
                continue
        return out

    def _external_refs_from_body(self, body: str) -> list[Artifact]:
        out: list[Artifact] = []
        seen: set[str] = set()
        for url in extract_urls(body):
            lower = url.lower()
            if lower.startswith("https://github.com/") and (
                "/issues/" in lower or "/pull/" in lower
            ):
                continue
            if any(lower.endswith(ext) or f"{ext}?" in lower for ext in IMAGE_EXTS):
                continue
            if "user-images.githubusercontent.com" in lower or "github.com/user-attachments/" in lower:
                continue
            if url in seen:
                continue
            seen.add(url)
            kind = ArtifactKind.DESIGN if any(h in lower for h in DESIGN_HOSTS) else ArtifactKind.URL
            out.append(Artifact(kind=kind, url=url, title=url))
        return out

    def _mentions_to_artifacts(self, body: str) -> list[Artifact]:
        return [
            Artifact(kind=ArtifactKind.MENTION, title=f"@{name}", url=f"https://github.com/{name}")
            for name in extract_mentions(body)
        ]
