from __future__ import annotations

import subprocess
from pathlib import Path

from gg.tasks.connectors.base import FetchOptions
from gg.tasks.connectors.github import GitHubConnector
from gg.tasks.normalizer import normalize
from tests.tasks.test_github_connector import FIXTURES, _fake_runner


def _full_bundle(monkeypatch):
    monkeypatch.setattr(
        subprocess, "run",
        _fake_runner({
            "42": "issue_42.json",
            "41": "issue_41.json",
            "40": "issue_40.json",
        }),
    )
    connector = GitHubConnector()
    ref = GitHubConnector.parse_ref("acme/web#42")
    return connector.fetch(ref, FetchOptions(max_depth=2))


def test_normalize_basic_fields(monkeypatch):
    bundle = _full_bundle(monkeypatch)
    task = normalize(bundle, include_raw=False)

    assert task.source.platform == "github"
    assert task.source.external_id == "42"
    assert task.source.url.endswith("/issues/42")
    assert task.task.title == "Add dark mode toggle"
    assert task.task.status == "open"
    assert task.task.author == "alice"
    assert "bob" in task.task.assignees
    assert task.task.labels == ["feature", "ui"]


def test_normalize_infers_type_and_priority_from_labels(monkeypatch):
    bundle = _full_bundle(monkeypatch)
    task = normalize(bundle)

    assert task.task.type == "feature"
    assert task.task.priority == "normal"


def test_normalize_extracts_acceptance_checklist(monkeypatch):
    bundle = _full_bundle(monkeypatch)
    task = normalize(bundle)

    assert "Toggle visible in settings" in task.task.description_markdown
    assert task.context.acceptance_criteria == [
        "Toggle visible in settings",
        "Persists across reloads",
    ]


def test_normalize_includes_comments_and_linked(monkeypatch):
    bundle = _full_bundle(monkeypatch)
    task = normalize(bundle)

    comment_authors = [c.title for c in task.context.comments]
    assert "alice" in comment_authors

    linked_titles = [lt.title for lt in task.context.linked_tasks]
    assert "Theme context provider" in linked_titles
    assert "Settings screen polish" in linked_titles


def test_normalize_classifies_design_and_images(monkeypatch):
    bundle = _full_bundle(monkeypatch)
    task = normalize(bundle)

    attachment_urls = {a.url for a in task.context.attachments}
    assert any("user-images.githubusercontent.com" in (u or "") for u in attachment_urls)

    external_kinds = {e.kind for e in task.context.external_refs}
    assert "design" in external_kinds
    assert "mention" in external_kinds


def test_normalize_json_roundtrip(monkeypatch):
    import json

    bundle = _full_bundle(monkeypatch)
    task = normalize(bundle, include_raw=False)
    parsed = json.loads(task.to_json(include_raw=False))

    assert parsed["schema_version"] == "1.0"
    assert parsed["source"]["platform"] == "github"
    assert parsed["task"]["type"] == "feature"
