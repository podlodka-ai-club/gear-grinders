"""Raw platform-neutral bundle produced by a connector before normalization.

A connector's only job is to fill a RawTaskBundle: pull the task, its
comments, attachments, linked tasks, external URLs, mentions -- each becomes
an `Artifact` with the appropriate `kind`. The universal `Artifact` type is
what lets GitHub, Jira, Redmine, and Pixso-style artifact sources all flow
through the same downstream pipeline.

The normalizer (`gg.tasks.normalizer`) then converts RawTaskBundle ->
CanonicalTask deterministically, without LLMs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ArtifactKind(str, Enum):
    """What an Artifact represents. Drives normalizer bucketing into
    `comments` / `linked_tasks` / `attachments` / `external_refs`.
    """
    LINKED_TASK = "linked_task"     # another task in any tracker
    COMMENT = "comment"             # comment on the root task
    ATTACHMENT = "attachment"       # generic file attachment
    IMAGE = "image"                 # image file (by extension)
    DESIGN = "design"               # Figma/Pixso/Miro/Whimsical link
    RECORDING = "recording"         # audio/video
    URL = "url"                     # plain external URL
    CODE_REF = "code_ref"           # reference to a PR/commit/file
    MENTION = "mention"             # @user reference


@dataclass
class Artifact:
    """A single piece of data a connector collected about a task.

    The tree of Artifacts is the connector's output before normalization.
    `children` is used mainly for LINKED_TASK nodes to represent depth-N
    traversal; leaf kinds (COMMENT, URL, MENTION, ...) usually have no
    children.

    `metadata` is platform-specific and opaque to the normalizer except for
    well-known keys: `number`, `state`, `labels`, `assignees`, `author`,
    `created_at`, `updated_at`, `depth`, `local_path`.
    """
    kind: ArtifactKind
    title: str = ""
    url: str | None = None
    content: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    children: list["Artifact"] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "title": self.title,
            "url": self.url,
            "content": self.content,
            "metadata": self.metadata,
            "children": [c.to_dict() for c in self.children],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Artifact":
        return cls(
            kind=ArtifactKind(data["kind"]),
            title=data.get("title", ""),
            url=data.get("url"),
            content=data.get("content"),
            metadata=data.get("metadata", {}),
            children=[cls.from_dict(c) for c in data.get("children", [])],
        )

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()


@dataclass
class RawTaskBundle:
    """Everything a connector collected, platform-neutral shape.

    `root` is the task itself (kind=LINKED_TASK). `artifacts` is the flat
    sidecar list of comments/attachments/external refs at depth 0. Nested
    linked tasks hang off `root.children`.

    `visited_refs` records every source_ref the connector touched during
    traversal -- useful for cycle-protection audit and for consumers that
    want to see the full reach of the fetch.
    """
    platform: str
    source_ref: str
    fetched_at: datetime
    root: Artifact
    artifacts: list[Artifact] = field(default_factory=list)
    max_depth: int = 0
    visited_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "source_ref": self.source_ref,
            "fetched_at": self.fetched_at.isoformat(),
            "max_depth": self.max_depth,
            "visited_refs": self.visited_refs,
            "root": self.root.to_dict(),
            "artifacts": [a.to_dict() for a in self.artifacts],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RawTaskBundle":
        return cls(
            platform=data["platform"],
            source_ref=data["source_ref"],
            fetched_at=datetime.fromisoformat(data["fetched_at"]),
            root=Artifact.from_dict(data["root"]),
            artifacts=[Artifact.from_dict(a) for a in data.get("artifacts", [])],
            max_depth=data.get("max_depth", 0),
            visited_refs=list(data.get("visited_refs", [])),
        )
