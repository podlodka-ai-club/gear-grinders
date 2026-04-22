"""TaskConnector interface: platform-specific fetching of raw task data."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from gg.tasks.schema.raw import RawTaskBundle


@dataclass(frozen=True)
class Ref:
    """Parsed task reference. `raw` is what the user typed, `normalized` is canonical."""
    platform: str
    raw: str
    normalized: str
    project: str = ""          # owner/repo for GH, JIRA project key, Redmine project slug
    external_id: str = ""      # issue number / key tail / ticket id


@dataclass
class FetchOptions:
    max_depth: int = 2
    download_assets: bool = False
    assets_dir: Path | None = None
    include_comments: bool = True
    include_linked: bool = True


class TaskConnector(ABC):
    """Fetch a task and its connected artifacts from an issue tracker."""

    platform: str = ""

    @classmethod
    @abstractmethod
    def can_handle(cls, ref: str) -> bool:
        """Return True if this connector recognizes the given reference string."""

    @classmethod
    @abstractmethod
    def parse_ref(cls, ref: str) -> Ref:
        """Parse a raw reference into a normalized Ref. Raises ValueError on bad input."""

    @abstractmethod
    def fetch(self, ref: Ref, options: FetchOptions) -> RawTaskBundle:
        """Fetch the task bundle. Must respect options.max_depth and cycle-protect."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if required CLI/credentials are present."""
