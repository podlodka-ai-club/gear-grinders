"""Canonical task JSON: platform-neutral, fed into the agent pipeline.

This module defines the stable JSON contract between the fetcher and every
downstream consumer (planner, implementer, reviewer, enrichment). The shape
is documented in `docs/canonical-task.md` and a real example lives at
`docs/examples/github-290.json`.

Stability guarantees:
    - `schema_version` bumps on breaking changes.
    - New optional fields may be added without a bump.
    - No field is silently renamed.

Agents should read `source`, `task`, `context`. The `raw` field carries the
original RawTaskBundle and is meant for debugging only.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

SCHEMA_VERSION = "1.0"


@dataclass
class SourceInfo:
    """Where the task came from. Identity + provenance."""
    platform: str
    external_id: str
    url: str
    fetched_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "external_id": self.external_id,
            "url": self.url,
            "fetched_at": self.fetched_at.isoformat(),
        }


@dataclass
class TaskCore:
    """Core fields an agent needs to act on the task.

    `type` and `priority` are inferred from labels via fixed alias tables
    (see normalizer.TYPE_LABELS / PRIORITY_LABELS). When no label matches,
    values default to `"unknown"` / `"normal"` and enrichment may override.
    Other fields come from the tracker unmodified, except `status` which is
    normalized to `open | in_progress | closed`.
    """
    title: str
    description_markdown: str
    type: str = "unknown"                # feature|bug|chore|docs|refactor|unknown
    priority: str = "normal"             # low|normal|high|critical
    status: str = "open"                 # open|in_progress|closed
    labels: list[str] = field(default_factory=list)
    assignees: list[str] = field(default_factory=list)
    author: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "description_markdown": self.description_markdown,
            "type": self.type,
            "priority": self.priority,
            "status": self.status,
            "labels": self.labels,
            "assignees": self.assignees,
            "author": self.author,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


@dataclass
class CanonicalArtifact:
    """Uniform shape for everything in `context`: comments, linked tasks,
    attachments, external refs, and their nested children.

    `kind` selects the interpretation:
      - `linked_task` -- another tracker task; `content` is its body.
      - `comment` -- root-task comment; `title` is author login.
      - `attachment` / `image` / `recording` -- files.
      - `design` -- design-tool link (Figma/Pixso/Miro/Whimsical).
      - `url` -- plain external URL.
      - `code_ref` -- PR/commit/file reference.
      - `mention` -- @user; `url` is their profile page.

    `metadata.local_path` appears if `--download-assets` stored the file.
    """
    kind: str
    title: str = ""
    url: str | None = None
    content: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    children: list["CanonicalArtifact"] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "title": self.title,
            "url": self.url,
            "content": self.content,
            "metadata": self.metadata,
            "children": [c.to_dict() for c in self.children],
        }


@dataclass
class TaskContext:
    """Secondary data the agent needs for good decisions.

    - `acceptance_criteria`: `- [ ]` checklist items from the body first;
      if none, lines under a `## Acceptance Criteria` / `## Definition of
      Done` / `## DoD` section. Empty when the body has neither.
    - `comments`: root-task comments only.
    - `linked_tasks`: cross-referenced tasks discovered in the body and in
      comment bodies, recursively up to the requested depth. Children are
      nested; see the traversal rules in docs/canonical-task.md.
    - `attachments`: files and images attached to the task.
    - `external_refs`: URLs, design-tool links, @mentions, code refs.
    """
    acceptance_criteria: list[str] = field(default_factory=list)
    comments: list[CanonicalArtifact] = field(default_factory=list)
    linked_tasks: list[CanonicalArtifact] = field(default_factory=list)
    attachments: list[CanonicalArtifact] = field(default_factory=list)
    external_refs: list[CanonicalArtifact] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "acceptance_criteria": self.acceptance_criteria,
            "comments": [c.to_dict() for c in self.comments],
            "linked_tasks": [c.to_dict() for c in self.linked_tasks],
            "attachments": [c.to_dict() for c in self.attachments],
            "external_refs": [c.to_dict() for c in self.external_refs],
        }


@dataclass
class CanonicalTask:
    """Top-level canonical JSON. See docs/canonical-task.md for the full spec.

    Produced by `gg task fetch`, consumed by every downstream agent step.
    Agents should read `source`, `task`, `context` and ignore `raw`.
    """
    source: SourceInfo
    task: TaskCore
    context: TaskContext = field(default_factory=TaskContext)
    raw: dict[str, Any] | None = None
    schema_version: str = SCHEMA_VERSION

    def to_dict(self, *, include_raw: bool = True) -> dict[str, Any]:
        out: dict[str, Any] = {
            "schema_version": self.schema_version,
            "source": self.source.to_dict(),
            "task": self.task.to_dict(),
            "context": self.context.to_dict(),
        }
        if include_raw and self.raw is not None:
            out["raw"] = self.raw
        return out

    def to_json(self, *, indent: int = 2, include_raw: bool = True) -> str:
        return json.dumps(self.to_dict(include_raw=include_raw), indent=indent, ensure_ascii=False)
