from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from gg.tasks.connectors.base import FetchOptions
from gg.tasks.connectors.github import GitHubConnector
from gg.tasks.schema.raw import ArtifactKind

FIXTURES = Path(__file__).parent / "fixtures" / "github"


class _FakeCompleted:
    def __init__(self, stdout: str, returncode: int = 0, stderr: str = ""):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


def _fake_runner(fixture_map: dict[str, str]):
    """Return a subprocess.run stand-in that serves JSON from fixtures by issue number."""

    def runner(args, **_kwargs):
        assert args[0:3] == ["gh", "issue", "view"]
        number = args[3]
        if number not in fixture_map:
            return _FakeCompleted("", returncode=1, stderr=f"not found: {number}")
        text = (FIXTURES / fixture_map[number]).read_text(encoding="utf-8")
        return _FakeCompleted(text, returncode=0)

    return runner


def test_parse_ref_full():
    ref = GitHubConnector.parse_ref("acme/web#42")
    assert ref.project == "acme/web"
    assert ref.external_id == "42"
    assert ref.normalized == "acme/web#42"


def test_parse_ref_url():
    ref = GitHubConnector.parse_ref("https://github.com/acme/web/pull/7")
    assert ref.normalized == "acme/web#7"


def test_parse_ref_invalid_raises():
    with pytest.raises(ValueError):
        GitHubConnector.parse_ref("not-a-ref")


def test_fetch_depth_zero(monkeypatch):
    monkeypatch.setattr(
        subprocess, "run",
        _fake_runner({"42": "issue_42.json"}),
    )

    connector = GitHubConnector()
    ref = GitHubConnector.parse_ref("acme/web#42")
    bundle = connector.fetch(ref, FetchOptions(max_depth=0))

    assert bundle.platform == "github"
    assert bundle.source_ref == "acme/web#42"
    assert bundle.root.title == "Add dark mode toggle"
    assert bundle.root.metadata["state"] == "open"
    assert bundle.root.metadata["labels"] == ["feature", "ui"]
    assert bundle.root.metadata["author"] == "alice"
    assert bundle.root.children == []  # no traversal at depth 0

    kinds = [a.kind for a in bundle.artifacts]
    assert ArtifactKind.COMMENT in kinds
    assert ArtifactKind.IMAGE in kinds
    assert ArtifactKind.DESIGN in kinds
    assert ArtifactKind.MENTION in kinds


def test_fetch_depth_two_traverses_links(monkeypatch):
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
    bundle = connector.fetch(ref, FetchOptions(max_depth=2))

    linked_titles = sorted(c.title for c in bundle.root.children)
    assert "Theme context provider" in linked_titles
    assert "Settings screen polish" in linked_titles

    theme = next(c for c in bundle.root.children if c.title == "Theme context provider")
    assert theme.children == []
    assert "acme/web#42" in bundle.visited_refs
    assert "acme/web#41" in bundle.visited_refs


def test_fetch_follows_links_found_in_comments(monkeypatch):
    monkeypatch.setattr(
        subprocess, "run",
        _fake_runner({
            "100": "issue_100.json",
            "101": "issue_101.json",
            "102": "issue_102.json",
        }),
    )

    connector = GitHubConnector()
    ref = GitHubConnector.parse_ref("acme/web#100")
    bundle = connector.fetch(ref, FetchOptions(max_depth=1))

    linked_titles = sorted(c.title for c in bundle.root.children)
    assert "Same problem via URL reference" in linked_titles
    assert "Same problem short ref" in linked_titles


def test_fetch_cycle_protection(monkeypatch):
    cyclic_42 = json.loads((FIXTURES / "issue_42.json").read_text())
    cyclic_42["body"] = "refers back to acme/web#42 itself"
    cyclic_path = FIXTURES / "_tmp_cyclic_42.json"
    cyclic_path.write_text(json.dumps(cyclic_42), encoding="utf-8")

    try:
        monkeypatch.setattr(
            subprocess, "run",
            _fake_runner({"42": "_tmp_cyclic_42.json"}),
        )
        connector = GitHubConnector()
        ref = GitHubConnector.parse_ref("acme/web#42")
        bundle = connector.fetch(ref, FetchOptions(max_depth=2))

        assert bundle.visited_refs == ["acme/web#42"]
        assert bundle.root.children == []
    finally:
        cyclic_path.unlink(missing_ok=True)
