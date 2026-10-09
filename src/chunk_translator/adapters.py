import asyncio
import tempfile
from pathlib import Path

from .prompts import SYSTEM


class AdapterError(Exception):
    pass


class Adapter:
    """Runs one stateless prompt through an installed CLI and returns the text answer."""

    name = ""

    def __init__(self, model: str | None = None):
        self.model = model

    def command(self, workdir: Path, prompt: str) -> tuple[list[str], str | None]:
        """Return (argv, stdin_text)."""
        raise NotImplementedError

    def read_output(self, workdir: Path, stdout: str) -> str:
        return stdout

    async def run(self, prompt: str, timeout: float) -> str:
        # Empty cwd so project instruction files (CLAUDE.md / AGENTS.md) are not picked up.
        with tempfile.TemporaryDirectory(prefix="ctrans-") as tmp:
            workdir = Path(tmp)
            argv, stdin_text = self.command(workdir, prompt)
            try:
                proc = await asyncio.create_subprocess_exec(
                    *argv,
                    cwd=workdir,
                    stdin=asyncio.subprocess.PIPE if stdin_text is not None else asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            except FileNotFoundError as e:
                raise AdapterError(f"{argv[0]} not found on PATH") from e
            try:
                out, err = await asyncio.wait_for(
                    proc.communicate(stdin_text.encode() if stdin_text is not None else None), timeout
                )
            except TimeoutError:
                proc.kill()
                await proc.wait()
                raise AdapterError(f"{self.name} timed out after {timeout:.0f}s")
            if proc.returncode != 0:
                tail = err.decode(errors="replace").strip()[-500:]
                raise AdapterError(f"{self.name} exited with {proc.returncode}: {tail}")
            return self.read_output(workdir, out.decode(errors="replace"))


class CodexAdapter(Adapter):
    name = "codex"

    def command(self, workdir, prompt):
        argv = ["codex", "exec", "--skip-git-repo-check", "--ephemeral", "-s", "read-only",
                "-C", str(workdir), "-o", str(workdir / "answer.txt")]
        if self.model:
            argv += ["-m", self.model]
        return argv + ["-"], f"{SYSTEM}\n\n{prompt}"

    def read_output(self, workdir, stdout):
        answer = workdir / "answer.txt"
        if not answer.exists():
            raise AdapterError("codex produced no final message")
        return answer.read_text()


class ClaudeAdapter(Adapter):
    name = "claude"

    def command(self, workdir, prompt):
        argv = ["claude", "-p", "--tools", "", "--no-session-persistence", "--system-prompt", SYSTEM]
        if self.model:
            argv += ["--model", self.model]
        return argv, prompt


class CursorAdapter(Adapter):
    name = "cursor"

    def command(self, workdir, prompt):
        # cursor-agent takes the prompt as an argument; ask mode is read-only.
        # --trust only accepts our own empty temp dir (it does not enable commands like --force).
        argv = ["cursor-agent", "-p", "--output-format", "text", "--mode", "ask", "--trust"]
        if self.model:
            argv += ["--model", self.model]
        return argv + [f"{SYSTEM}\n\n{prompt}"], None


ADAPTERS = {a.name: a for a in (CodexAdapter, ClaudeAdapter, CursorAdapter)}


def get_adapter(engine: str, model: str | None) -> Adapter:
    try:
        return ADAPTERS[engine](model)
    except KeyError:
        raise AdapterError(f"unknown engine {engine!r}; choose from {', '.join(ADAPTERS)}") from None
