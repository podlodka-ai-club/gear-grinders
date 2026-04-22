from datetime import datetime, timezone

from gg.tasks.schema import (
    Artifact,
    ArtifactKind,
    CanonicalArtifact,
    CanonicalTask,
    RawTaskBundle,
    SourceInfo,
    TaskContext,
    TaskCore,
)
from gg.tasks.schema.canonical import SCHEMA_VERSION


def _sample_bundle() -> RawTaskBundle:
    linked = Artifact(
        kind=ArtifactKind.LINKED_TASK,
        title="Dependency task",
        url="https://example.com/issues/2",
        metadata={"link_type": "blocks"},
        children=[
            Artifact(kind=ArtifactKind.COMMENT, title="note", content="WIP"),
        ],
    )
    root = Artifact(
        kind=ArtifactKind.LINKED_TASK,
        title="Root task",
        url="https://example.com/issues/1",
        content="Body text",
        metadata={"number": 1},
    )
    return RawTaskBundle(
        platform="github",
        source_ref="owner/repo#1",
        fetched_at=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
        root=root,
        artifacts=[
            linked,
            Artifact(kind=ArtifactKind.COMMENT, title="alice", content="LGTM"),
            Artifact(kind=ArtifactKind.IMAGE, url="https://cdn/x.png"),
        ],
        max_depth=2,
        visited_refs=["owner/repo#1", "owner/repo#2"],
    )


def test_raw_bundle_roundtrip():
    bundle = _sample_bundle()
    data = bundle.to_dict()
    restored = RawTaskBundle.from_dict(data)

    assert restored.platform == "github"
    assert restored.source_ref == "owner/repo#1"
    assert restored.max_depth == 2
    assert restored.visited_refs == ["owner/repo#1", "owner/repo#2"]
    assert restored.fetched_at == bundle.fetched_at
    assert restored.root.kind is ArtifactKind.LINKED_TASK
    assert len(restored.artifacts) == 3
    assert restored.artifacts[0].children[0].content == "WIP"
    assert restored.to_dict() == data


def test_artifact_walk_visits_children():
    bundle = _sample_bundle()
    linked = bundle.artifacts[0]
    all_kinds = [a.kind for a in linked.walk()]

    assert all_kinds == [ArtifactKind.LINKED_TASK, ArtifactKind.COMMENT]


def test_canonical_task_json_includes_schema_version():
    canonical = CanonicalTask(
        source=SourceInfo(
            platform="github",
            external_id="1",
            url="https://example.com/issues/1",
            fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
        task=TaskCore(
            title="Task",
            description_markdown="Do it",
            labels=["bug"],
            type="bug",
        ),
        context=TaskContext(
            acceptance_criteria=["it works"],
            comments=[CanonicalArtifact(kind="comment", title="alice", content="nice")],
        ),
    )
    data = canonical.to_dict(include_raw=False)

    assert data["schema_version"] == SCHEMA_VERSION
    assert data["source"]["platform"] == "github"
    assert data["task"]["type"] == "bug"
    assert data["context"]["acceptance_criteria"] == ["it works"]
    assert "raw" not in data


def test_canonical_task_to_json_is_valid_json():
    canonical = CanonicalTask(
        source=SourceInfo(
            platform="github", external_id="1", url="u",
            fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
        task=TaskCore(title="t", description_markdown=""),
    )
    import json
    parsed = json.loads(canonical.to_json())

    assert parsed["task"]["title"] == "t"
