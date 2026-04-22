"""Connector registry: resolves a raw ref to the right connector."""
from __future__ import annotations

from gg.tasks.connectors.base import Ref, TaskConnector


class ConnectorRegistry:
    def __init__(self) -> None:
        self._by_platform: dict[str, type[TaskConnector]] = {}

    def register(self, connector_cls: type[TaskConnector]) -> None:
        if not connector_cls.platform:
            raise ValueError(f"{connector_cls.__name__} has empty platform attribute")
        self._by_platform[connector_cls.platform] = connector_cls

    def by_platform(self, platform: str) -> type[TaskConnector]:
        try:
            return self._by_platform[platform]
        except KeyError as e:
            known = ", ".join(sorted(self._by_platform)) or "(none)"
            raise ValueError(f"Unknown platform '{platform}'. Known: {known}") from e

    def resolve(self, ref: str, *, platform: str | None = None) -> tuple[type[TaskConnector], Ref]:
        """Find the connector that handles `ref`. If `platform` set, force it."""
        if platform and platform != "auto":
            cls = self.by_platform(platform)
            return cls, cls.parse_ref(ref)

        for cls in self._by_platform.values():
            if cls.can_handle(ref):
                return cls, cls.parse_ref(ref)

        known = ", ".join(sorted(self._by_platform)) or "(none)"
        raise ValueError(f"No connector recognizes ref '{ref}'. Registered: {known}")

    def platforms(self) -> list[str]:
        return sorted(self._by_platform)


_registry = ConnectorRegistry()


def get_connector(ref: str, *, platform: str | None = None) -> tuple[TaskConnector, Ref]:
    _ensure_default_connectors()
    cls, parsed = _registry.resolve(ref, platform=platform)
    return cls(), parsed


def register(connector_cls: type[TaskConnector]) -> None:
    _registry.register(connector_cls)


def registered_platforms() -> list[str]:
    _ensure_default_connectors()
    return _registry.platforms()


_initialized = False


def _ensure_default_connectors() -> None:
    global _initialized
    if _initialized:
        return
    from gg.tasks.connectors.github import GitHubConnector
    from gg.tasks.connectors.jira import JiraConnector
    from gg.tasks.connectors.redmine import RedmineConnector

    for cls in (GitHubConnector, JiraConnector, RedmineConnector):
        if cls.platform not in _registry._by_platform:
            _registry.register(cls)
    _initialized = True
