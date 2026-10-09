import argparse
import asyncio
import sys
import time
from pathlib import Path

from .adapters import ADAPTERS, AdapterError, get_adapter
from .prompts import build_glossary_prompt
from .runner import Translator, log


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def write_text(path: Path | None, text: str) -> None:
    if path is None:
        sys.stdout.write(text)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    log(f"wrote {path}")


def cmd_translate(args) -> None:
    raw = args.input.read_text(encoding="utf-8")
    lines = raw.splitlines()
    glossary = args.glossary.read_text(encoding="utf-8") if args.glossary else None
    translator = Translator(
        get_adapter(args.engine, args.model), glossary, args.cache_dir,
        jobs=args.jobs, retries=args.retries, timeout=args.timeout, context=args.context_lines,
    )
    started = time.monotonic()
    out = asyncio.run(translator.translate(lines, args.chunk_lines))
    write_text(args.output, "\n".join(out) + ("\n" if raw.endswith("\n") else ""))
    log(f"total {time.monotonic() - started:.0f}s")


def cmd_glossary(args) -> None:
    adapter = get_adapter(args.engine, args.model)
    started = time.monotonic()
    answer = asyncio.run(adapter.run(build_glossary_prompt(read_lines(args.input)), args.timeout))
    if not answer.strip():
        raise SystemExit("empty glossary response")
    write_text(args.output, answer.strip() + "\n")
    log(f"glossary done in {time.monotonic() - started:.0f}s")


def main() -> None:
    p = argparse.ArgumentParser(prog="ctrans", description="Translate long text in chunks via AI CLIs.")
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp):
        sp.add_argument("input", type=Path)
        sp.add_argument("-o", "--output", type=Path, help="output file (default: stdout)")
        sp.add_argument("--engine", choices=list(ADAPTERS), default="codex")
        sp.add_argument("--model", help="model name passed to the CLI (default: CLI's own default)")
        sp.add_argument("--timeout", type=float, default=600, help="seconds per CLI call")

    t = sub.add_parser("translate", help="translate a file")
    common(t)
    t.add_argument("--glossary", type=Path, help="glossary/notes file injected into every chunk prompt")
    t.add_argument("--jobs", type=int, default=3, help="parallel CLI calls")
    t.add_argument("--chunk-lines", type=int, default=55)
    t.add_argument("--context-lines", type=int, default=5)
    t.add_argument("--retries", type=int, default=2)
    t.add_argument("--cache-dir", type=Path, default=Path(".ctrans/cache"))
    t.set_defaults(func=cmd_translate)

    g = sub.add_parser("glossary", help="draft a glossary (people, terms, likely STT errors)")
    common(g)
    g.set_defaults(func=cmd_glossary)

    args = p.parse_args()
    try:
        args.func(args)
    except AdapterError as e:
        raise SystemExit(f"error: {e}")
