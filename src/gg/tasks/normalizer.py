"""Shared, deterministic RawTaskBundle -> CanonicalTask mapping.

No LLM, no inference by semantics -- only structural mapping, pattern matching
on labels/metadata, and checklist extraction. Enrichment happens in a later
stage on top of the canonical form.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Iterable

from gg.tasks.schema.canonical import (
    CanonicalArtifact,
    CanonicalTask,
    SourceInfo,
    TaskContext,
    TaskCore,
)
from gg.tasks.schema.raw import Artifact, ArtifactKind, RawTaskBundle

CHECKBOX_RE = re.compile(r"^\s*[-*]\s*\[\s?\]\s+(.+?)\s*$", re.MULTILINE)
ACCEPTANCE_SECTION_RE = re.compile(
    r"(?ims)^##+\s*(acceptance(?:\s+criteria)?|definition\s+of\s+done|dod)\b[^\n]*\n(.+?)(?=^##+\s|\Z)",
)

TYPE_LABELS: dict[str, tuple[str, ...]] = {
    "bug": ("bug", "defect", "regression"),
    "feature": ("feature", "enhancement", "feat"),
    "chore": ("chore", "maintenance", "tech-debt", "refactor-safe"),
    "docs": ("docs", "documentation"),
    "refactor": ("refactor", "cleanup"),
}
PRIORITY_LABELS: dict[str, tuple[str, ...]] = {
    "critical": ("critical", "p0", "sev-0", "urgent"),
    "high": ("high", "p1", "sev-1", "important"),
    "low": ("low", "p3", "sev-3", "nice-to-have"),
}


def normalize(bundle: RawTaskBundle, *, include_raw: bool = True) -> CanonicalTask:
    root_meta = bundle.root.metadata

    source = SourceInfo(
        platform=bundle.platform,
        external_id=str(root_meta.get("number", "") or root_meta.get("external_id", "")),
        url=bundle.root.url or "",
        fetched_at=bundle.fetched_at,
    )

    labels = list(root_meta.get("labels", []))
    body = bundle.root.content or ""

    task = TaskCore(
        title=bundle.root.title,
        description_markdown=body,
        type=_infer_type(labels),
        priority=_infer_priority(labels),
        status=_normalize_status(root_meta.get("state", "open")),
        labels=labels,
        assignees=list(root_meta.get("assignees", [])),
        author=root_meta.get("author", "") or "",
        created_at=_parse_dt(root_meta.get("created_at", "")),
        updated_at=_parse_dt(root_meta.get("updated_at", "")),
    )

    context = TaskContext(
        acceptance_criteria=_extract_acceptance(body),
        comments=[_to_canonical(a) for a in _filter(bundle.artifacts, ArtifactKind.COMMENT)],
        linked_tasks=[_to_canonical(a) for a in bundle.root.children],
        attachments=[
            _to_canonical(a)
            for a in _filter(bundle.artifacts, ArtifactKind.ATTACHMENT, ArtifactKind.IMAGE)
        ],
        external_refs=[
            _to_canonical(a)
            for a in _filter(bundle.artifacts, ArtifactKind.URL, ArtifactKind.DESIGN,
                             ArtifactKind.RECORDING, ArtifactKind.MENTION, ArtifactKind.CODE_REF)
        ],
    )

    return CanonicalTask(
        source=source,
        task=task,
        context=context,
        raw=bundle.to_dict() if include_raw else None,
    )


def _filter(artifacts: Iterable[Artifact], *kinds: ArtifactKind) -> list[Artifact]:
    kind_set = set(kinds)
    return [a for a in artifacts if a.kind in kind_set]


def _to_canonical(artifact: Artifact) -> CanonicalArtifact:
    return CanonicalArtifact(
        kind=artifact.kind.value,
        title=artifact.title,
        url=artifact.url,
        content=artifact.content,
        metadata=dict(artifact.metadata),
        children=[_to_canonical(c) for c in artifact.children],
    )


def _infer_type(labels: list[str]) -> str:
    lowered = {la.lower() for la in labels}
    for task_type, aliases in TYPE_LABELS.items():
        if lowered & set(aliases):
            return task_type
    return "unknown"


def _infer_priority(labels: list[str]) -> str:
    lowered = {la.lower() for la in labels}
    for priority, aliases in PRIORITY_LABELS.items():
        if lowered & set(aliases):
            return priority
    return "normal"


def _normalize_status(state: str) -> str:
    s = (state or "").lower()
    if s in ("open", "opened", "new", "in progress", "in_progress"):
        return "open" if s in ("open", "opened", "new") else "in_progress"
    if s in ("closed", "done", "resolved", "completed", "merged"):
        return "closed"
    return s or "open"


def _parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _extract_acceptance(body: str) -> list[str]:
    """Pull acceptance criteria: checklist items first, then lines under an Acceptance section."""
    if not body:
        return []

    items: list[str] = []
    seen: set[str] = set()

    for m in CHECKBOX_RE.finditer(body):
        item = m.group(1).strip()
        if item and item not in seen:
            seen.add(item)
            items.append(item)

    if items:
        return items

    m = ACCEPTANCE_SECTION_RE.search(body)
    if m:
        for line in m.group(2).splitlines():
            stripped = line.strip().lstrip("-*").strip()
            if stripped and stripped not in seen:
                seen.add(stripped)
                items.append(stripped)

    return items
