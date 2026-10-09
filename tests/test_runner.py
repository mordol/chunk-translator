import asyncio
import re

from chunk_translator.adapters import Adapter
from chunk_translator.runner import Translator


class FakeAdapter(Adapter):
    """Echoes '[Lnnn] 번역:<text>' for requested lines; can misbehave on demand."""

    name = "fake"

    def __init__(self, fail_first=0, drop_if_over=None):
        super().__init__(None)
        self.calls = 0
        self.fail_first = fail_first
        self.drop_if_over = drop_if_over

    async def run(self, prompt, timeout):
        self.calls += 1
        section = prompt.split("Lines to translate:\n", 1)[1].split("\n\n", 1)[0]
        pairs = re.findall(r"^\[(L\d+)\] (.*)$", section, re.M)
        if self.calls <= self.fail_first or (self.drop_if_over and len(pairs) > self.drop_if_over):
            pairs = pairs[:-1]  # drop a line -> validation error
        return "\n".join(f"[{i}] 번역:{t}" for i, t in pairs)


def run(adapter, lines, tmp_path, **kw):
    t = Translator(adapter, None, tmp_path, jobs=2, retries=1, timeout=5, **kw)
    t_sleep = asyncio.sleep
    async def no_sleep(_): await t_sleep(0)
    asyncio.sleep = no_sleep
    try:
        return asyncio.run(t.translate(lines, chunk_lines=4))
    finally:
        asyncio.sleep = t_sleep


LINES = ["one two three four", "", "five six seven eight", "a", "b", "c", "d"]


def test_preserves_line_count_and_blank_lines(tmp_path):
    out = run(FakeAdapter(), LINES, tmp_path)
    assert len(out) == len(LINES) and out[1] == ""
    assert out[0] == "번역:one two three four"


def test_retry_after_invalid_answer(tmp_path):
    adapter = FakeAdapter(fail_first=1)
    out = run(adapter, LINES, tmp_path)
    assert out[6] == "번역:d" and adapter.calls == 3  # 2 chunks + 1 retry


def test_split_when_chunk_keeps_failing(tmp_path):
    adapter = FakeAdapter(drop_if_over=2)
    out = run(adapter, LINES, tmp_path)
    assert all(o.startswith("번역:") for o in out if o)


def test_cache_skips_finished_chunks(tmp_path):
    run(FakeAdapter(), LINES, tmp_path)
    again = FakeAdapter()
    run(again, LINES, tmp_path)
    assert again.calls == 0
