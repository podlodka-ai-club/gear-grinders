# CanonicalTask -- reference

The `CanonicalTask` JSON is the platform-neutral contract between the fetcher
and everything downstream (planner, implementer, reviewer). It is produced by
`gg task fetch` and lives at `.gg/tasks/<ref>/task.json`.

**Design rule:** the normalizer is deterministic. Nothing in this document
requires an LLM to produce. If a field is empty/unknown, a later enrichment
stage fills it -- the fetcher does not guess.

## Top-level shape

```json
{
  "schema_version": "1.0",
  "source":  { ... },
  "task":    { ... },
  "context": { ... },
  "raw":     { ... }
}
```

| Field | Purpose |
|-------|---------|
| `schema_version` | Bump on breaking changes. Consumers should check. |
| `source` | Where the task came from. Identity + provenance. |
| `task` | Core fields an agent needs to act: title, description, type, priority, status, people, dates. |
| `context` | Everything else useful for reasoning: acceptance criteria, comments, linked tasks, attachments, external references. |
| `raw` | The full `RawTaskBundle` that produced this canonical form. For audit/debugging only. **Agents should not read `raw`.** Can be suppressed with `--no-raw`. |

## `source`

```json
{
  "platform": "github",
  "external_id": "290",
  "url": "https://github.com/zilliztech/claude-context/issues/290",
  "fetched_at": "2026-04-22T11:07:57.211087+00:00"
}
```

| Field | Notes |
|-------|-------|
| `platform` | `github` / `jira` / `redmine`. Authoritative. |
| `external_id` | Platform-local id (issue number, Jira key tail, Redmine ticket id). |
| `url` | Human-browsable URL to the source task. |
| `fetched_at` | ISO-8601 UTC. Treat data as a snapshot at this moment. |

## `task`

Core fields. All authoritative for whatever the tracker exposes; inferred
fields (`type`, `priority`) are marked best-effort below.

```json
{
  "title": "...",
  "description_markdown": "...",
  "type": "feature",
  "priority": "normal",
  "status": "open",
  "labels": ["feature", "ui"],
  "assignees": ["bob"],
  "author": "alice",
  "created_at": "2026-01-10T12:00:00+00:00",
  "updated_at": "2026-01-12T08:30:00+00:00"
}
```

| Field | Authoritative? | Notes |
|-------|----------------|-------|
| `title` | yes | Platform title, unmodified. |
| `description_markdown` | yes | Platform body. GitHub returns markdown natively; Jira/Redmine will be rendered to markdown. |
| `type` | best-effort | Inferred from `labels` via a fixed alias table (see below). `unknown` if no label matched. Enrichment stage may override. |
| `priority` | best-effort | Same as `type`, from priority labels. `normal` if nothing matched. |
| `status` | yes | Normalized to one of: `open`, `in_progress`, `closed`. |
| `labels` | yes | As-is, order preserved. |
| `assignees` | yes | Platform logins. |
| `author` | yes | Platform login. |
| `created_at`, `updated_at` | yes | ISO-8601, UTC. May be null if the platform doesn't expose it. |

### Type inference table

| Canonical type | Label aliases (case-insensitive) |
|----------------|-----------------------------------|
| `bug` | `bug`, `defect`, `regression` |
| `feature` | `feature`, `enhancement`, `feat` |
| `chore` | `chore`, `maintenance`, `tech-debt`, `refactor-safe` |
| `docs` | `docs`, `documentation` |
| `refactor` | `refactor`, `cleanup` |
| `unknown` | none of the above matched |

### Priority inference table

| Canonical priority | Label aliases |
|--------------------|---------------|
| `critical` | `critical`, `p0`, `sev-0`, `urgent` |
| `high` | `high`, `p1`, `sev-1`, `important` |
| `low` | `low`, `p3`, `sev-3`, `nice-to-have` |
| `normal` | default if nothing matched |

If the tables don't fit your labels, extend them in `normalizer.py`.

## `context`

Secondary, but load-bearing for good decisions.

```json
{
  "acceptance_criteria": ["Toggle visible in settings", "..."],
  "comments":       [ CanonicalArtifact, ... ],
  "linked_tasks":   [ CanonicalArtifact, ... ],
  "attachments":    [ CanonicalArtifact, ... ],
  "external_refs":  [ CanonicalArtifact, ... ]
}
```

| Field | How it's populated |
|-------|--------------------|
| `acceptance_criteria` | Pulled from `description_markdown`. First, all `- [ ]` / `* [ ]` checklist items in the order they appear. If none exist, lines under a `## Acceptance Criteria` / `## Definition of Done` / `## DoD` section. Empty list means no explicit criteria -- agent must infer. |
| `comments` | Each comment from the tracker as a `CanonicalArtifact` of `kind: "comment"`. Only root-task comments at depth 0. |
| `linked_tasks` | Every cross-referenced task the connector could reach, recursively up to `--depth`. See *Depth and traversal* below. |
| `attachments` | Files/images attached to the task (body attachments on GitHub, `attachments[]` on Jira/Redmine). |
| `external_refs` | URLs, design tool links (Figma/Pixso/Miro/Whimsical), @mentions, and other non-task references. |

## `CanonicalArtifact`

The uniform shape used in `comments`, `linked_tasks`, `attachments`,
`external_refs`, and nested `children`:

```json
{
  "kind": "linked_task",
  "title": "...",
  "url": "https://...",
  "content": "...",
  "metadata": { ... },
  "children": [ CanonicalArtifact, ... ]
}
```

| `kind` | Meaning |
|--------|---------|
| `linked_task` | Another tracker task. `content` is its markdown body. `metadata` carries number/state/labels/author/dates/depth. `children` is the next level of traversal. |
| `comment` | Comment on the root task. `title` is author login, `content` is body. |
| `attachment` | Generic file. |
| `image` | Image attachment (PNG/JPG/GIF/WebP/SVG). |
| `design` | Design-tool link (Figma, Pixso, Miro, Whimsical). |
| `recording` | Audio/video. |
| `url` | Plain external URL. |
| `code_ref` | Reference to a PR, commit, or file. |
| `mention` | `@user` mention. `url` points to the user's profile. |

`metadata.local_path` is set if `--download-assets` stored the asset on disk.

## Depth and traversal

`--depth N` controls how far the connector walks linked tasks.

- `depth 0`: just the root task, its comments, its body attachments/refs.
- `depth 1`: also follow links from the root body **and its comments**; each
  linked task is fetched, but its own comments are not traversed.
- `depth 2`: the default. Follow links two levels deep.

Cycle protection: `visited_refs` is tracked globally; a ref already seen is
skipped. You can inspect `raw.visited_refs` for audit.

Linked tasks found inside comments are followed too -- this is how we pull
in "same problem, see #289 and #215" references the author added post-hoc.

## Agent guide

If you are an agent consuming `task.json`:

1. **Read `task` and `context`. Ignore `raw`** unless you are debugging the
   fetcher itself.
2. If `task.type == "unknown"` or `task.priority == "normal"` with no labels,
   trust your judgment -- the fetcher did not infer. Look at the title/body.
3. **Acceptance criteria**: if `context.acceptance_criteria` is non-empty,
   those are explicit and must be met. If empty, derive them from
   `description_markdown` yourself.
4. **Linked tasks** give historical and parallel context. Their `content`
   field is the body of the linked task at fetch time -- it may already
   describe the root cause or a proposed fix (see the zilliztech example).
5. **Don't blindly follow every `external_refs.url`** -- some are log
   fragments accidentally captured by the URL regex. Treat them as hints.

## Example

A pruned real capture of `zilliztech/claude-context#290` lives at
`docs/examples/github-290.json`. That is the shape you will actually see.
