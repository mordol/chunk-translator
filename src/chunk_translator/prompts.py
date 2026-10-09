from .chunker import Chunk

# Bump when prompt wording changes so cached results are invalidated.
PROMPT_VERSION = "1"

SYSTEM = "You are a professional English-to-Korean translator. Output only what is requested, with no commentary."

POLICY = """\
Translate the English meeting transcript lines into natural Korean.

Rules:
- Tone: polite conversational Korean (대화체 존댓말, "~요/~습니다"), as if spoken to an audience of parents.
- Remove meaningless fillers and stutters (um, uh, repeated words like "this this") so the Korean reads naturally.
- The text is speech-to-text output. Correct obvious recognition errors only when the context makes the
  intended word clear (e.g. a misspelled well-known author name, a currency symbol that is clearly a weight).
  If unsure, translate as written.
- Keep person names, school names, place names and other proper nouns in English (e.g. Sarah, Riverside Academy, RA).
- Keep a strict 1:1 line mapping. A sentence may be split across lines; put the corresponding part on each line.
  Never merge or split lines.
- If a line contains only fillers (e.g. "Um."), output the id with an empty translation.
"""

FORMAT = """\
Output format:
- Exactly one output line per input line, in the same order: [Lnnn] <Korean translation>
- Output ONLY those lines. No preamble, no explanations, no code fences.
- Do NOT output the reference lines.
"""


def build_translate_prompt(chunk: Chunk, glossary: str | None, feedback: str | None = None) -> str:
    parts = [POLICY]
    if glossary:
        parts.append(f"Glossary and notes (follow these):\n{glossary.strip()}\n")
    if chunk.context:
        ref = "\n".join(f"[{i}] {t}" for i, t in chunk.context)
        parts.append(f"Reference lines (preceding context, already translated elsewhere; DO NOT translate):\n{ref}\n")
    lines = "\n".join(f"[{i}] {t}" for i, t in zip(chunk.ids, chunk.lines))
    parts.append(f"Lines to translate:\n{lines}\n")
    parts.append(FORMAT)
    if feedback:
        parts.append(f"Your previous answer was rejected: {feedback}\nFix this and answer again in the required format.\n")
    return "\n".join(parts)


GLOSSARY_PROMPT = """\
Below is an English meeting transcript produced by speech-to-text. It will be translated into Korean in
separate chunks, so we need shared notes to keep the translation consistent.

Produce a concise Markdown glossary with these sections:
## People
- Name — role (unify spelling variants, e.g. "Jon/John → John" if they are the same person)
## Proper nouns
- Names of the school, places, programs (kept in English in the translation)
## Recurring terms
- English term → Korean translation to use consistently (events, school-specific terms)
## Likely speech-to-text errors
- "as transcribed" → intended word (only include ones that are clear from context)

Output only the Markdown, nothing else.

Transcript:
{text}
"""


def build_glossary_prompt(lines: list[str]) -> str:
    return GLOSSARY_PROMPT.format(text="\n".join(lines))
