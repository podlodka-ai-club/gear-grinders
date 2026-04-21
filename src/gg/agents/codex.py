from __future__ import annotations

import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

from gg.agents.base import AgentBackend

CODEX_TIMEOUT = 600
MAX_RETRIES = 1

SKIP_PREFIXES = (
    "Reading additional",
    "OpenAI Codex",
    "--------",
    "hook:",
    "tokens used",
)


def _stream_stderr(proc: subprocess.Popen, console, stop_event: threading.Event) -> None:
    """Read Codex stderr line by line and print interesting lines."""
    if not proc.stderr:
        return
    for raw_line in proc.stderr:
        if stop_event.is_set():
            break
        line = raw_line.strip()
        if not line:
            continue
        if any(line.startswith(p) for p in SKIP_PREFIXES):
            continue
        if line.startswith("workdir:") or line.startswith("model:") or line.startswith("provider:"):
            console.print(f"    [dim]{line}[/dim]")
        elif line.startswith("approval:") or line.startswith("sandbox:") or line.startswith("session id:"):
            continue
        elif line.startswith("reasoning"):
            continue
        elif line.startswith("user"):
            console.print(f"    [blue]> prompt sent[/blue]")
        elif line.startswith("codex"):
            console.print(f"    [green]< generating response...[/green]")
        else:
            console.print(f"    [dim]{line[:120]}[/dim]")


class CodexAgent(AgentBackend):
    def __init__(self, console=None):
        self._console = console

    def generate(self, prompt: str, *, cwd: str | None = None) -> str:
        out_path = Path(tempfile.mktemp(suffix=".md"))

        for attempt in range(MAX_RETRIES + 1):
            try:
                if self._console:
                    output = self._run_streaming(prompt, out_path, cwd)
                else:
                    output = self._run_silent(prompt, out_path, cwd)

                if output:
                    return output
                if attempt < MAX_RETRIES:
                    continue
                return ""
            except subprocess.TimeoutExpired:
                out_path.unlink(missing_ok=True)
                if attempt < MAX_RETRIES:
                    continue
                raise RuntimeError(f"Codex timed out after {CODEX_TIMEOUT}s")
            except RuntimeError:
                out_path.unlink(missing_ok=True)
                if attempt < MAX_RETRIES:
                    continue
                raise
        return ""

    def _run_streaming(self, prompt: str, out_path: Path, cwd: str | None) -> str:
        stop_event = threading.Event()
        proc = subprocess.Popen(
            ["codex", "exec", "-o", str(out_path), prompt],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
        )

        reader = threading.Thread(
            target=_stream_stderr,
            args=(proc, self._console, stop_event),
            daemon=True,
        )
        reader.start()

        try:
            proc.wait(timeout=CODEX_TIMEOUT)
        except subprocess.TimeoutExpired:
            stop_event.set()
            proc.kill()
            proc.wait()
            raise

        stop_event.set()
        reader.join(timeout=2)

        output = ""
        if out_path.exists():
            output = out_path.read_text(encoding="utf-8").strip()
            out_path.unlink(missing_ok=True)

        if not output and proc.returncode != 0:
            stderr = proc.stderr.read() if proc.stderr else ""
            raise RuntimeError(f"Codex failed (rc={proc.returncode}): {stderr[:200]}")

        return output

    def _run_silent(self, prompt: str, out_path: Path, cwd: str | None) -> str:
        result = subprocess.run(
            ["codex", "exec", "-o", str(out_path), prompt],
            capture_output=True,
            text=True,
            timeout=CODEX_TIMEOUT,
            cwd=cwd,
        )
        output = ""
        if out_path.exists():
            output = out_path.read_text(encoding="utf-8").strip()
            out_path.unlink(missing_ok=True)

        if not output and result.returncode != 0:
            raise RuntimeError(f"Codex failed: {result.stderr.strip()[:200]}")
        return output

    def is_available(self) -> bool:
        return shutil.which("codex") is not None
