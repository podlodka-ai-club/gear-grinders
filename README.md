# gg -- Agent Orchestrator

Pipeline: backlog task -> research -> implementation -> PR -> review.

## Task fetcher

`gg task fetch` pulls an issue from a tracker (GitHub now; Jira and Redmine
are connector stubs ready to be filled in) and produces a platform-neutral
canonical JSON that downstream agent steps consume.

**Docs**: [docs/canonical-task.md](docs/canonical-task.md) -- full field
reference and agent guide. Example output:
[docs/examples/github-290.json](docs/examples/github-290.json).

### Architecture

Two layers, one shared normalizer:

```
Connector (per-platform)  ->  RawTaskBundle  ->  Normalizer (shared)  ->  CanonicalTask
```

- **RawTaskBundle** keeps everything the connector could collect. A universal
  `Artifact` type (`LINKED_TASK`, `COMMENT`, `ATTACHMENT`, `IMAGE`, `DESIGN`,
  `RECORDING`, `URL`, `CODE_REF`, `MENTION`) lets GitHub issues, Redmine
  journals, Jira issue-links, or Pixso embeds all flow through the same shape.
- **CanonicalTask** is the stable JSON (`schema_version: 1.0`) the agent sees.
  Fields: `source`, `task` (title/description/type/priority/status/labels/
  assignees/author/dates), `context` (acceptance_criteria, comments,
  linked_tasks, attachments, external_refs), and optional `raw`.

The normalizer is **deterministic** -- label-based type/priority inference,
checklist and `## Acceptance` section extraction, platform-state mapping. No
LLM here. Smart enrichment (linked-task summaries, implicit requirements,
code references) belongs to a later pipeline stage on top of CanonicalTask.

### Usage

```bash
gg task fetch acme/web#42                        # auto-detect (github)
gg task fetch PROJ-123 --platform jira           # stub for work-time
gg task fetch redmine:12345 --platform redmine   # stub for work-time
gg task fetch acme/web#42 --depth 2 --download-assets
gg task fetch acme/web#42 --stdout --no-raw | jq .task

gg task show .gg/tasks/acme_web_42/task.json
```

Defaults: `--depth 2`, assets URL-only, output to `.gg/tasks/<ref>/task.json`.

### Supported platforms

| Platform | Connector | Auth | Status |
|----------|-----------|------|--------|
| GitHub   | `gh` CLI  | `gh auth login` | working |
| Jira     | REST v3   | basic-auth via env | stub |
| Redmine  | REST      | `X-Redmine-API-Key` env | stub |

Both stubs carry implementation plans in their module docstrings.

### Depth & cycle protection

`--depth N` walks linked tasks recursively. Depth 0 = just the task itself and
its own comments/attachments. Every visited `source_ref` is tracked to prevent
loops; repeat references are skipped.

### Adding a new connector

1. Subclass `TaskConnector` in `src/gg/tasks/connectors/`.
2. Implement `can_handle`, `parse_ref`, `is_available`, `fetch`.
3. Add to `_ensure_default_connectors()` in
   `src/gg/tasks/connectors/registry.py`.
4. Write tests under `tests/tasks/` using fixture JSON.
