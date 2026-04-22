"""Redmine connector stub.

Implementation plan (for work-time):
    - Auth: REDMINE_BASE_URL + REDMINE_API_KEY (header `X-Redmine-API-Key`).
    - Fetch: GET /issues/{id}.json?include=journals,relations,attachments,children
      - description -> root content (textile/markdown depending on instance; keep as-is)
      - tracker.name -> metadata.tracker (for type inference)
      - priority.name -> metadata.priority
      - relations[] -> LINKED_TASK with metadata.link_type = relation_type
      - children[] -> LINKED_TASK with metadata.link_type = 'subtask'
      - attachments[] -> ATTACHMENT / IMAGE
      - journals[].notes -> COMMENT
      - custom_fields -> metadata.custom_fields (parse 'Acceptance Criteria' separately)
    - Pixso/other design links are regular URLs inside description -> normalizer classifies.
"""
from __future__ import annotations

import re

from gg.tasks.connectors.base import FetchOptions, Ref, TaskConnector
from gg.tasks.schema.raw import RawTaskBundle

REDMINE_REF_RE = re.compile(r"^redmine:(\d+)$", re.IGNORECASE)


class RedmineConnector(TaskConnector):
    platform = "redmine"

    @classmethod
    def can_handle(cls, ref: str) -> bool:
        return bool(REDMINE_REF_RE.match(ref.strip()))

    @classmethod
    def parse_ref(cls, ref: str) -> Ref:
        m = REDMINE_REF_RE.match(ref.strip())
        if not m:
            raise ValueError(f"Not a Redmine ref: {ref!r} (expected redmine:12345)")
        return Ref(
            platform=cls.platform,
            raw=ref,
            normalized=f"redmine:{m.group(1)}",
            project="",
            external_id=m.group(1),
        )

    def is_available(self) -> bool:
        return False

    def fetch(self, ref: Ref, options: FetchOptions) -> RawTaskBundle:
        raise NotImplementedError(
            "RedmineConnector is a stub. Implement REST client (see module docstring).",
        )
