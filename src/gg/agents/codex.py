from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from gg.agents.base import AgentBackend

CODEX_TIMEOUT = 300
MAX_RETRIES = 1


class CodexAgent(AgentBackend):
    def generate(self, prompt: str, *, cwd: str | None = None) -> str:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as out:
            out_path = out.name

        for attempt in range(MAX_RETRIES + 1):
            try:
                result = subprocess.run(
                    ["codex", "exec", "-o", out_path, prompt],
                    capture_output=True,
                    text=True,
                    timeout=CODEX_TIMEOUT,
                    cwd=cwd,
                )
                output = Path(out_path).read_text(encoding="utf-8").strip()
                if result.returncode == 0 and output:
                    return output
                if output:
                    return output
                if attempt < MAX_RETRIES:
                    continue
                if result.stderr.strip():
                    raise RuntimeError(f"Codex failed: {result.stderr.strip()}")
                return result.stdout.strip()
            except subprocess.TimeoutExpired:
                if attempt < MAX_RETRIES:
                    continue
                raise RuntimeError(f"Codex timed out after {CODEX_TIMEOUT}s")
            finally:
                Path(out_path).unlink(missing_ok=True)
        return ""

    def is_available(self) -> bool:
        return shutil.which("codex") is not None
