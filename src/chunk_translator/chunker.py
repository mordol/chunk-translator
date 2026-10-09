from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    index: int
    ids: list[str]  # IDs of lines to translate, e.g. "L042"
    lines: list[str]  # source text for each id
    context: list[tuple[str, str]]  # (id, text) of preceding lines, reference only


def line_id(n: int, width: int) -> str:
    """1-based line number -> ID like 'L042'."""
    return f"L{n:0{width}d}"


def id_width(total_lines: int) -> int:
    return max(3, len(str(total_lines)))


def make_chunks(lines: list[str], size: int = 55, context: int = 5) -> list[Chunk]:
    """Split lines into chunks of translatable (non-blank) lines.

    Blank lines are never sent; the caller keeps them as-is. Each chunk carries
    the last `context` translatable lines before it as read-only reference.
    """
    width = id_width(len(lines))
    items = [(line_id(i + 1, width), text) for i, text in enumerate(lines) if text.strip()]
    chunks = []
    for start in range(0, len(items), size):
        part = items[start : start + size]
        chunks.append(
            Chunk(
                index=len(chunks),
                ids=[i for i, _ in part],
                lines=[t for _, t in part],
                context=items[max(0, start - context) : start],
            )
        )
    return chunks


def split_chunk(chunk: Chunk, context: int = 5) -> tuple[Chunk, Chunk]:
    """Halve a chunk (used when a chunk keeps failing validation)."""
    mid = len(chunk.ids) // 2
    first = Chunk(chunk.index, chunk.ids[:mid], chunk.lines[:mid], chunk.context)
    preceding = (chunk.context + list(zip(first.ids, first.lines)))[-context:] if context else []
    second = Chunk(chunk.index, chunk.ids[mid:], chunk.lines[mid:], preceding)
    return first, second
