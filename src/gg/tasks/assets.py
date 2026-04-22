"""Asset downloader: fetches IMAGE/ATTACHMENT URLs from a RawTaskBundle.

Kept intentionally minimal -- uses urllib (stdlib) so we don't pull `requests`
as a hard dep for this feature. Skips everything it cannot fetch and records
the reason in metadata. Opt-in via FetchOptions.download_assets.
"""
from __future__ import annotations

import hashlib
import mimetypes
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from gg.tasks.schema.raw import Artifact, ArtifactKind, RawTaskBundle

DOWNLOADABLE_KINDS = frozenset({ArtifactKind.IMAGE, ArtifactKind.ATTACHMENT, ArtifactKind.RECORDING})
MAX_BYTES = 20 * 1024 * 1024  # 20 MB cap per asset
USER_AGENT = "gear-grinders/0.1 (+task-fetcher)"


@dataclass
class DownloadStats:
    attempted: int = 0
    downloaded: int = 0
    skipped: int = 0
    failed: int = 0


def download_assets(bundle: RawTaskBundle, target_dir: Path) -> DownloadStats:
    """Walk the bundle, download downloadable artifacts into target_dir.

    Mutates artifacts in place: sets metadata['local_path'] on success,
    metadata['download_error'] on failure.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    stats = DownloadStats()

    for artifact in _iter_all(bundle):
        if artifact.kind not in DOWNLOADABLE_KINDS or not artifact.url:
            continue
        stats.attempted += 1

        filename = _filename_for(artifact.url)
        local_path = target_dir / filename

        if local_path.exists():
            artifact.metadata["local_path"] = str(local_path)
            stats.skipped += 1
            continue

        try:
            _download(artifact.url, local_path)
            artifact.metadata["local_path"] = str(local_path)
            stats.downloaded += 1
        except Exception as e:  # noqa: BLE001 - recorded per-artifact
            artifact.metadata["download_error"] = str(e)[:200]
            stats.failed += 1

    return stats


def _iter_all(bundle: RawTaskBundle):
    yield from bundle.root.walk()
    for a in bundle.artifacts:
        yield from a.walk()


def _filename_for(url: str) -> str:
    parsed = urlparse(url)
    tail = Path(parsed.path).name or "asset"
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    if "." not in tail:
        ext = mimetypes.guess_extension(mimetypes.guess_type(url)[0] or "") or ""
        tail = f"{tail}{ext}"
    return f"{digest}_{tail}"


def _download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - URLs come from tracker body
            if getattr(resp, "status", 200) >= 400:
                raise RuntimeError(f"HTTP {resp.status}")
            content = resp.read(MAX_BYTES + 1)
    except urllib.error.URLError as e:
        raise RuntimeError(f"fetch failed: {e.reason}") from e

    if len(content) > MAX_BYTES:
        raise RuntimeError(f"asset exceeds {MAX_BYTES} bytes")

    dest.write_bytes(content)
