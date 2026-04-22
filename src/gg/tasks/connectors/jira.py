"""Jira connector stub.

Implementation plan (for work-time):
    - Auth: Atlassian API token via env (JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN),
      basic auth header `email:token` base64, over REST v3.
    - Fetch: GET /rest/api/3/issue/{key}?expand=renderedFields,names,changelog
      - description (ADF -> markdown via simple walker)
      - fields.issuelinks -> LINKED_TASK artifacts (outwardIssue/inwardIssue)
      - fields.subtasks -> LINKED_TASK with metadata.link_type='subtask'
      - fields.parent -> LINKED_TASK (epic link)
      - fields.attachment -> ATTACHMENT / IMAGE by content-type
    - Comments: GET /rest/api/3/issue/{key}/comment?expand=renderedBody
    - Custom fields: scan `names` for 'Acceptance Criteria' / 'Definition of Done'.
    - Rate limits: honor Retry-After header.
"""
from __future__ import annotations

import re

from gg.tasks.connectors.base import FetchOptions, Ref, TaskConnector
from gg.tasks.schema.raw import RawTaskBundle

JIRA_KEY_RE = re.compile(r"^([A-Z][A-Z0-9]+)-(\d+)$")


class JiraConnector(TaskConnector):
    platform = "jira"

    @classmethod
    def can_handle(cls, ref: str) -> bool:
        return bool(JIRA_KEY_RE.match(ref.strip()))

    @classmethod
    def parse_ref(cls, ref: str) -> Ref:
        m = JIRA_KEY_RE.match(ref.strip())
        if not m:
            raise ValueError(f"Not a Jira key: {ref!r} (expected PROJECT-123)")
        return Ref(
            platform=cls.platform,
            raw=ref,
            normalized=f"{m.group(1)}-{m.group(2)}",
            project=m.group(1),
            external_id=m.group(2),
        )

    def is_available(self) -> bool:
        return False

    def fetch(self, ref: Ref, options: FetchOptions) -> RawTaskBundle:
        raise NotImplementedError(
            "JiraConnector is a stub. Implement REST v3 client (see module docstring).",
        )
