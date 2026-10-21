# chunk-translator

Translate long text files by splitting them into chunks and running each chunk through an
AI coding CLI you already have installed — **Codex**, **Claude Code**, or **Cursor Agent** — as
independent, stateless calls in parallel.

## Why

Asking a single interactive agent session to translate a few hundred lines is slow and fragile:
the source text, the generated translation, and the file-write tool calls all pile up in one
context window, which eventually forces context compaction — and compaction loses the terminology
and tone decisions made earlier.

`chunk-translator` avoids this by:

- sending each chunk in a **fresh, tool-less CLI call** (no context accumulation),
- injecting a shared **glossary** into every chunk to keep names, terms and tone consistent,
- **validating** every response line-by-line and retrying or splitting chunks that fail,
- **caching** finished chunks so a rerun only redoes what failed.

On a ~450-line meeting transcript this takes about 1.5 minutes with Claude (9 chunks, 3 in parallel).

## Requirements

- Python 3.11+ and [uv](https://docs.astral.sh/uv/)
- At least one of these CLIs installed and logged in:
  - `codex` (OpenAI Codex CLI) — default engine
  - `claude` (Claude Code)
  - `cursor-agent` (Cursor Agent CLI)

No API keys are handled by this tool; it uses whatever authentication each CLI already has.

## Install

```sh
git clone <this-repo>
cd chunk-translator
uv sync
uv run ctrans --help
```

## Usage

```sh
# 1. (Optional) Draft a glossary from the whole input, then review/edit it by hand.
uv run ctrans glossary input.txt -o out/glossary.md

# 2. Translate, injecting the glossary into every chunk prompt.
uv run ctrans translate input.txt -o out/input.ko.txt --glossary out/glossary.md

# Choose another engine / model
uv run ctrans translate input.txt -o out/input.ko.txt --engine claude --model sonnet
uv run ctrans translate input.txt -o out/input.ko.txt --engine cursor
```

Progress, per-chunk timings and validation failures are printed to stderr. If any chunk still
fails after retries, the command exits non-zero; simply rerun it — completed chunks are served
from the cache.

### Options

| Option | Default | Description |
|---|---|---|
| `--engine` | `codex` | `codex`, `claude`, or `cursor` |
| `--model` | CLI default | Model name passed through to the CLI |
| `--glossary` | — | Text/Markdown file injected verbatim into every chunk prompt (`translate` only) |
| `--jobs` | `3` | Number of parallel CLI calls |
| `--chunk-lines` | `55` | Max lines per chunk |
| `--context-lines` | `5` | Preceding lines sent as read-only context |
| `--retries` | `2` | Retries per chunk before splitting it in half |
| `--timeout` | `600` | Seconds per CLI call |
| `--cache-dir` | `.ctrans/cache` | Where finished chunks are cached |
| `-o, --output` | stdout | Output file |

## How it works

1. **Chunking** — Non-blank lines get stable IDs (`L001`, `L002`, …) and are grouped into chunks.
   Blank lines are never sent and are kept as-is. Each chunk also carries the last few lines of
   the previous chunk as *reference only* context.
2. **Prompting** — The prompt contains the translation policy, the glossary, the reference lines and
   the lines to translate in `[Lnnn] text` form. The model must answer with exactly one
   `[Lnnn] translation` line per input line.
3. **CLI call** — Each call runs in an empty temporary directory (so project instruction files like
   `CLAUDE.md` / `AGENTS.md` are not picked up), with tools disabled or read-only:
   - `codex exec --skip-git-repo-check --ephemeral -s read-only -o <file> -`
   - `claude -p --tools "" --no-session-persistence --system-prompt ...`
   - `cursor-agent -p --output-format text --mode ask --trust` (trusts only the empty temp dir)
4. **Validation** — The response is rejected if any ID is missing, duplicated, out of order, or
   belongs to the reference lines; if there is any text outside `[Lnnn]` lines (preambles,
   explanations); or if a line of 4+ words comes back without any Korean. A rejected answer is
   retried with the reason appended to the prompt; after repeated failures the chunk is split in
   half and each half is retried.
5. **Caching & merge** — Each validated chunk is stored under `.ctrans/cache/`, keyed by the chunk
   content, context, glossary, prompt version, engine and model. The final output has exactly the
   same number of lines as the input.

## Default translation policy

The built-in prompt (`src/chunk_translator/prompts.py`) is tuned for **English → Korean
speech-to-text meeting transcripts**:

- polite conversational Korean (대화체 존댓말),
- fillers and stutters (`um`, `uh`, repeated words) are dropped; filler-only lines become empty,
- obvious speech-recognition errors are corrected only when the context makes them clear,
- names and proper nouns stay in English,
- strict 1:1 line mapping — sentences split across lines stay split.

Adjust `POLICY` in `prompts.py` for other languages or content types, and bump `PROMPT_VERSION`
so cached chunks are invalidated.

## Limitations

- Input is treated as plain text, one segment per line. Markdown structure, subtitles (SRT/VTT)
  and JSON are not parsed specially yet.
- The `glossary` command sends the whole input in one call; very large inputs may exceed the
  model's context.
- CLI flags can change between CLI releases; if an engine fails, check its `--help` output against
  `src/chunk_translator/adapters.py`.

## Security notes

- **Untrusted input (prompt injection).** The input text and the glossary are sent to the model
  verbatim. The `claude` engine runs with all tools disabled, but the `codex` (`-s read-only`) and
  `cursor` (`--mode ask`) engines only block writes — the agent can still *read* local files. A
  malicious input could try to make it print file contents into the translation. Response
  validation rejects anything outside the `[Lnnn]` lines, which limits but does not eliminate this.
  Prefer `--engine claude` for text from unknown sources.
- **Process arguments.** `cursor-agent` receives the prompt as a command-line argument, so the text
  being translated is visible to other local users via `ps` while it runs.
- **Plaintext cache.** Translations are cached unencrypted in `.ctrans/cache/`. Delete it after
  translating sensitive documents.

## Development

```sh
uv run pytest
```

Tests use a fake adapter, so they do not call any CLI.

## Project layout

```
src/chunk_translator/
  cli.py        # `ctrans translate` / `ctrans glossary`
  chunker.py    # line IDs, chunking, chunk splitting
  prompts.py    # translation policy and prompt builders
  adapters.py   # codex / claude / cursor-agent wrappers
  validate.py   # response parsing and validation
  runner.py     # parallel execution, retries, cache
tests/
```

## License

[MIT](LICENSE)
