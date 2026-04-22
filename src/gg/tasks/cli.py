"""CLI surface for the task fetcher: `gg task fetch` and `gg task show`."""
from __future__ import annotations

import json
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from gg.tasks.assets import download_assets
from gg.tasks.connectors import get_connector
from gg.tasks.connectors.base import FetchOptions
from gg.tasks.normalizer import normalize

PLATFORM_CHOICES = ("auto", "github", "jira", "redmine")


@click.group()
def task() -> None:
    """Fetch and normalize tasks from issue trackers."""


@task.command("fetch")
@click.argument("ref")
@click.option("--platform", type=click.Choice(PLATFORM_CHOICES), default="auto",
              help="Force a specific platform; default auto-detects from ref shape.")
@click.option("--depth", type=click.IntRange(0, 5), default=2, show_default=True,
              help="Max traversal depth for linked tasks.")
@click.option("--download-assets", "download_assets_flag", is_flag=True,
              help="Download images/attachments locally into <output-dir>/assets/.")
@click.option("-o", "--output", type=click.Path(dir_okay=False, writable=True),
              default=None,
              help="Write canonical JSON to this path. Default: .gg/tasks/<ref>/task.json")
@click.option("--stdout", "to_stdout", is_flag=True, help="Print canonical JSON to stdout instead of writing a file.")
@click.option("--no-raw", is_flag=True, help="Exclude the raw bundle from the canonical output.")
@click.option("--no-comments", is_flag=True, help="Skip comments.")
@click.option("--no-linked", is_flag=True, help="Skip linked-task traversal.")
def fetch_cmd(
    ref: str,
    platform: str,
    depth: int,
    download_assets_flag: bool,
    output: str | None,
    to_stdout: bool,
    no_raw: bool,
    no_comments: bool,
    no_linked: bool,
) -> None:
    """Fetch REF (e.g. owner/repo#42, PROJ-123, redmine:12345) into canonical JSON."""
    console = Console()
    try:
        connector, parsed_ref = get_connector(ref, platform=None if platform == "auto" else platform)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(2) from e

    if not connector.is_available():
        console.print(f"[red]{connector.platform} connector is not available (missing CLI/credentials).[/red]")
        raise SystemExit(3)

    out_path = Path(output) if output else _default_output_path(parsed_ref.normalized)
    assets_dir = out_path.parent / "assets"

    options = FetchOptions(
        max_depth=depth,
        download_assets=download_assets_flag,
        assets_dir=assets_dir if download_assets_flag else None,
        include_comments=not no_comments,
        include_linked=not no_linked,
    )

    console.print(f"[bold]Fetching[/bold] {parsed_ref.normalized} via {connector.platform} (depth={depth})...")
    bundle = connector.fetch(parsed_ref, options)
    console.print(
        f"  [green]root:[/green] {bundle.root.title!r}; "
        f"artifacts={len(bundle.artifacts)}; visited={len(bundle.visited_refs)}",
    )

    if download_assets_flag:
        console.print(f"  downloading assets -> {assets_dir}")
        stats = download_assets(bundle, assets_dir)
        console.print(
            f"  [green]assets:[/green] downloaded={stats.downloaded} "
            f"skipped(cached)={stats.skipped} failed={stats.failed}",
        )

    canonical = normalize(bundle, include_raw=not no_raw)
    rendered = canonical.to_json(include_raw=not no_raw)

    if to_stdout:
        click.echo(rendered)
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")
    console.print(f"  [green]wrote:[/green] {out_path}")


@task.command("show")
@click.argument("path", type=click.Path(exists=True, dir_okay=False))
def show_cmd(path: str) -> None:
    """Pretty-print a canonical task JSON file."""
    console = Console()
    data = json.loads(Path(path).read_text(encoding="utf-8"))

    src = data["source"]
    t = data["task"]
    ctx = data["context"]

    header = (
        f"[bold]{t['title']}[/bold]\n"
        f"{src['platform']}:{src['external_id']}  •  {t['type']}/{t['priority']}  •  {t['status']}\n"
        f"{src['url']}"
    )
    console.print(Panel(header, style="cyan"))

    meta = Table(show_header=False, box=None)
    meta.add_column(style="bold")
    meta.add_column()
    meta.add_row("Author", t.get("author", ""))
    meta.add_row("Assignees", ", ".join(t.get("assignees", [])) or "-")
    meta.add_row("Labels", ", ".join(t.get("labels", [])) or "-")
    meta.add_row("Created", t.get("created_at") or "-")
    meta.add_row("Updated", t.get("updated_at") or "-")
    console.print(meta)

    if ctx.get("acceptance_criteria"):
        console.print("\n[bold]Acceptance criteria[/bold]")
        for item in ctx["acceptance_criteria"]:
            console.print(f"  - {item}")

    linked = ctx.get("linked_tasks") or []
    if linked:
        console.print(f"\n[bold]Linked tasks ({len(linked)})[/bold]")
        for lt in linked:
            console.print(f"  - {lt.get('title', '')} -- {lt.get('url') or ''}")

    atts = ctx.get("attachments") or []
    if atts:
        console.print(f"\n[bold]Attachments ({len(atts)})[/bold]")
        for a in atts:
            local = a.get("metadata", {}).get("local_path")
            suffix = f" (local: {local})" if local else ""
            console.print(f"  - [{a['kind']}] {a.get('url')}{suffix}")

    ext = ctx.get("external_refs") or []
    if ext:
        console.print(f"\n[bold]External refs ({len(ext)})[/bold]")
        for e in ext:
            console.print(f"  - [{e['kind']}] {e.get('url') or e.get('title')}")


def _default_output_path(normalized_ref: str) -> Path:
    safe = normalized_ref.replace("/", "_").replace("#", "_").replace(":", "_")
    return Path(".gg") / "tasks" / safe / "task.json"


__all__ = ["task"]
