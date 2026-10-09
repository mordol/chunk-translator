import pytest

from chunk_translator.validate import ValidationError, parse_response

IDS = ["L001", "L002", "L003"]
SRC = ["Thank you for joining us this evening.", "Um.", "Next slide, please."]


def test_valid_response_allows_empty_filler_line():
    out = parse_response("[L001] 오늘 저녁 함께해 주셔서 감사합니다.\n[L002]\n[L003] 다음 슬라이드요.", IDS, SRC)
    assert out == {"L001": "오늘 저녁 함께해 주셔서 감사합니다.", "L002": "", "L003": "다음 슬라이드요."}


def test_code_fence_is_stripped():
    out = parse_response("```\n[L001] 감사합니다.\n[L002]\n[L003] 다음이요.\n```", IDS, SRC)
    assert out["L003"] == "다음이요."


@pytest.mark.parametrize("text, msg", [
    ("Here is the translation:\n[L001] 가\n[L002]\n[L003] 다", "unexpected text"),
    ("[L001] 가\n[L003] 다", "missing"),
    ("[L001] 가\n[L001] 가\n[L002]\n[L003] 다", "duplicate"),
    ("[L000] 참고\n[L001] 가\n[L002]\n[L003] 다", "unexpected ids"),
    ("[L002]\n[L001] 가\n[L003] 다", "out of order"),
    ("[L001] Thank you for joining us.\n[L002]\n[L003] 다", "untranslated"),
])
def test_rejections(text, msg):
    with pytest.raises(ValidationError, match=msg):
        parse_response(text, IDS, SRC)
