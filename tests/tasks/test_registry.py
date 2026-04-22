import pytest

from gg.tasks.connectors import get_connector
from gg.tasks.connectors.github import GitHubConnector
from gg.tasks.connectors.jira import JiraConnector
from gg.tasks.connectors.redmine import RedmineConnector


def test_github_auto_detect():
    connector, ref = get_connector("acme/web#42")
    assert isinstance(connector, GitHubConnector)
    assert ref.project == "acme/web"
    assert ref.external_id == "42"
    assert ref.normalized == "acme/web#42"


def test_github_url_auto_detect():
    _, ref = get_connector("https://github.com/acme/web/issues/42")
    assert ref.normalized == "acme/web#42"


def test_jira_auto_detect():
    connector, ref = get_connector("PROJ-123")
    assert isinstance(connector, JiraConnector)
    assert ref.project == "PROJ"
    assert ref.external_id == "123"


def test_redmine_auto_detect():
    connector, ref = get_connector("redmine:5555")
    assert isinstance(connector, RedmineConnector)
    assert ref.external_id == "5555"


def test_unknown_ref_raises():
    with pytest.raises(ValueError, match="No connector recognizes"):
        get_connector("garbage-ref")


def test_platform_override_forces_connector():
    connector, ref = get_connector("TEAM-7", platform="jira")
    assert isinstance(connector, JiraConnector)
    assert ref.normalized == "TEAM-7"


def test_platform_override_wrong_format_raises():
    with pytest.raises(ValueError):
        get_connector("totally-not-jira", platform="jira")
