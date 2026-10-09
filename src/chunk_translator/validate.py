import re

LINE_RE = re.compile(r"^\[(L\d+)\][ \t]?(.*)$")
HANGUL_RE = re.compile(r"[가-힣]")
# A source line with at least this many words must contain Hangul in its translation.
MIN_WORDS_FOR_HANGUL_CHECK = 4


class ValidationError(Exception):
    pass


def parse_response(text: str, expected_ids: list[str], sources: list[str]) -> dict[str, str]:
    """Parse '[Lnnn] translation' lines and check them against the request."""
    body = text.strip()
    # Models sometimes wrap the whole answer in a code fence.
    if body.startswith("```"):
        body = re.sub(r"^```[^\n]*\n|\n?```$", "", body).strip()

    result: dict[str, str] = {}
    order: list[str] = []
    for raw in body.splitlines():
        if not raw.strip():
            continue
        m = LINE_RE.match(raw.strip())
        if not m:
            raise ValidationError(f"unexpected text outside [Lnnn] lines: {raw.strip()[:80]!r}")
        lid, translated = m.group(1), m.group(2).strip()
        if lid in result:
            raise ValidationError(f"duplicate id {lid}")
        result[lid] = translated
        order.append(lid)

    expected = set(expected_ids)
    if missing := [i for i in expected_ids if i not in result]:
        raise ValidationError(f"missing ids: {', '.join(missing[:10])}")
    if extra := [i for i in order if i not in expected]:
        raise ValidationError(f"unexpected ids (do not translate reference lines): {', '.join(extra[:10])}")
    if order != expected_ids:
        raise ValidationError("ids are out of order")

    untranslated = [
        lid
        for lid, src in zip(expected_ids, sources)
        if len(src.split()) >= MIN_WORDS_FOR_HANGUL_CHECK and not HANGUL_RE.search(result[lid])
    ]
    if untranslated:
        raise ValidationError(f"lines left untranslated: {', '.join(untranslated[:10])}")
    return result
