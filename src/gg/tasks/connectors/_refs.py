"""Reference parsing: pull #N, owner/repo#N, JIRA-123 out of text bodies."""
from __future__ import annotations

import re
from dataclasses import dataclass

GH_FULL_RE = re.compile(r"\b([A-Za-z0-9._-]+/[A-Za-z0-9._-]+)#(\d+)\b")
GH_SHORT_RE = re.compile(r"(?<![A-Za-z0-9/])#(\d+)\b")
JIRA_RE = re.compile(r"\b([A-Z][A-Z0-9]+)-(\d+)\b")
URL_RE = re.compile(r"https?://[^\s)\]]+")
MENTION_RE = re.compile(r"(?<![\w])@([A-Za-z0-9][A-Za-z0-9_-]{0,38})\b")


@dataclass(frozen=True)
class ExtractedRef:
    platform: str
    normalized: str
    raw: str


def extract_refs(text: str, *, default_repo: str | None = None) -> list[ExtractedRef]:
    """Extract all task refs from free text. Dedupes, preserves first-seen order."""
    if not text:
        return []

    seen: set[str] = set()
    out: list[ExtractedRef] = []

    def _add(platform: str, normalized: str, raw: str) -> None:
        if normalized in seen:
            return
        seen.add(normalized)
        out.append(ExtractedRef(platform=platform, normalized=normalized, raw=raw))

    for m in GH_FULL_RE.finditer(text):
        _add("github", f"{m.group(1)}#{m.group(2)}", m.group(0))

    for m in JIRA_RE.finditer(text):
        _add("jira", f"{m.group(1)}-{m.group(2)}", m.group(0))

    for m in GH_SHORT_RE.finditer(text):
        number = m.group(1)
        if default_repo:
            _add("github", f"{default_repo}#{number}", m.group(0))
        else:
            _add("github", f"#{number}", m.group(0))

    return out


def extract_urls(text: str) -> list[str]:
    if not text:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for m in URL_RE.finditer(text):
        url = m.group(0).rstrip(".,;:")
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def extract_mentions(text: str) -> list[str]:
    if not text:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for m in MENTION_RE.finditer(text):
        name = m.group(1)
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out
