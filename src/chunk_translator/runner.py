import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path

from .adapters import Adapter, AdapterError
from .chunker import Chunk, id_width, line_id, make_chunks, split_chunk
from .prompts import PROMPT_VERSION, build_translate_prompt
from .validate import ValidationError, parse_response


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


class Translator:
    def __init__(self, adapter: Adapter, glossary: str | None, cache_dir: Path,
                 jobs: int = 3, retries: int = 2, timeout: float = 600, context: int = 5):
        self.adapter = adapter
        self.glossary = glossary
        self.cache_dir = cache_dir
        self.sem = asyncio.Semaphore(jobs)
        self.retries = retries
        self.timeout = timeout
        self.context = context

    def _cache_path(self, chunk: Chunk) -> Path:
        key = json.dumps([PROMPT_VERSION, self.adapter.name, self.adapter.model, self.glossary,
                          chunk.ids, chunk.lines, chunk.context])
        return self.cache_dir / f"{hashlib.sha256(key.encode()).hexdigest()[:24]}.json"

    async def _attempt(self, chunk: Chunk) -> dict[str, str]:
        """Try a chunk up to retries+1 times; raise the last error if all fail."""
        feedback = None
        for attempt in range(self.retries + 1):
            if attempt:
                await asyncio.sleep(2 ** attempt)
            prompt = build_translate_prompt(chunk, self.glossary, feedback)
            try:
                async with self.sem:
                    answer = await self.adapter.run(prompt, self.timeout)
                return parse_response(answer, chunk.ids, chunk.lines)
            except ValidationError as e:
                feedback = str(e)
                log(f"  chunk {chunk.index} ({chunk.ids[0]}-{chunk.ids[-1]}) invalid: {e}")
                last = e
            except AdapterError as e:
                log(f"  chunk {chunk.index} ({chunk.ids[0]}-{chunk.ids[-1]}) failed: {e}")
                last = e
        raise last

    async def translate_chunk(self, chunk: Chunk) -> dict[str, str]:
        cache = self._cache_path(chunk)
        if cache.exists():
            return json.loads(cache.read_text())
        started = time.monotonic()
        try:
            result = await self._attempt(chunk)
        except ValidationError:
            # Smaller requests are easier to get right; halve and retry once more.
            if len(chunk.ids) < 2:
                raise
            log(f"  chunk {chunk.index}: splitting {len(chunk.ids)} lines in half")
            first, second = split_chunk(chunk, self.context)
            parts = await asyncio.gather(self.translate_chunk(first), self.translate_chunk(second))
            result = {**parts[0], **parts[1]}
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(result, ensure_ascii=False, indent=1))
        log(f"chunk {chunk.index} ({chunk.ids[0]}-{chunk.ids[-1]}) done in {time.monotonic() - started:.0f}s")
        return result

    async def translate(self, lines: list[str], chunk_lines: int) -> list[str]:
        chunks = make_chunks(lines, chunk_lines, self.context)
        log(f"{len(lines)} lines -> {len(chunks)} chunks via {self.adapter.name}"
            f"{f' ({self.adapter.model})' if self.adapter.model else ''}")
        results = await asyncio.gather(*(self.translate_chunk(c) for c in chunks), return_exceptions=True)

        failed = [(c, r) for c, r in zip(chunks, results) if isinstance(r, BaseException)]
        if failed:
            for c, err in failed:
                log(f"FAILED chunk {c.index} ({c.ids[0]}-{c.ids[-1]}): {err}")
            raise SystemExit(f"{len(failed)} chunk(s) failed; rerun to retry (successful chunks are cached)")

        translated: dict[str, str] = {}
        for r in results:
            translated.update(r)
        width = id_width(len(lines))
        return [translated[line_id(n, width)] if text.strip() else text for n, text in enumerate(lines, 1)]
