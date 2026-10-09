from chunk_translator.chunker import make_chunks, split_chunk


def test_every_nonblank_line_appears_exactly_once():
    lines = [f"line {i}" if i % 7 else "" for i in range(1, 445)]
    chunks = make_chunks(lines, size=55, context=5)
    ids = [i for c in chunks for i in c.ids]
    assert len(ids) == len(set(ids)) == sum(1 for l in lines if l.strip())
    assert all(len(c.ids) <= 55 for c in chunks)


def test_context_is_preceding_lines():
    lines = [f"s{i}" for i in range(1, 21)]
    chunks = make_chunks(lines, size=8, context=3)
    assert chunks[0].context == []
    assert chunks[1].context == [("L006", "s6"), ("L007", "s7"), ("L008", "s8")]


def test_split_chunk_keeps_context_continuity():
    chunk = make_chunks([f"s{i}" for i in range(1, 11)], size=10, context=2)[0]
    a, b = split_chunk(chunk, context=2)
    assert a.ids + b.ids == chunk.ids
    assert b.context == [("L004", "s4"), ("L005", "s5")]
