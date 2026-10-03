# Proposal

## Why

passage-ranking ends with a numbered, budgeted context, but nothing turns
it into a report. This change adds the write stage: one streamed LLM call
that answers the query from the selected passages, cites each claim with
the passage number, and a code step that renders the citation markers and
the reference list in the user's chosen style. Writing options change only
this stage, so rewriting a finished run with another tone or citation style
is cheap.

## What Changes

- `src/wosarcher/stages/write.py` (pure): builds the messages, streams the
  answer through `on_delta`, checks every `[n]` against the context,
  renders markers by `citation_marker` (numeric, superscript,
  author-year), and appends a reference list by `reference_style` (APA,
  MLA, Chicago, IEEE) grouped by source, with heading path or pdf-ingest
  page ID for each cited passage.
- Prompts in `src/wosarcher/prompts/`: `write.md` (system message),
  `passages.md` (data preamble), `write_task.md` (final instruction), all
  filled with `string.Template` from trusted values only (query, tone,
  tone description, tone instructions, words, language); passage text is
  sent in a separate message inside a delimited block marked as data.
- `prompts/tones.toml`: the 11 tones (objective, formal, analytical,
  persuasive, informative, explanatory, descriptive, critical,
  comparative, speculative, reflective) with gpt-researcher's
  descriptions; `prompts.tones()` loads it. `tone_instructions` adds free
  text to the chosen tone.
- Contracts: `Reference`; `Report` fields `body`, `markdown`, `cited`,
  `references`, `warnings`.
- Unknown tones and reference styles fail before the LLM is called;
  unknown citation numbers become warnings and are removed from the
  rendered report.

## Non-goals

- No planner prompt (`prompts/plan.md` belongs to research-collection).
- No `wosarcher fork --from write` or CLI flags (run-orchestration wires
  options to the stage).
- No user-defined tones outside `prompts/tones.toml`.
- No citation styles beyond APA, MLA, Chicago, and IEEE, and no
  localisation of the "References" heading.
- No fact checking of claims against passages beyond the number check.

## Capabilities

### New Capabilities

- `report-writing`: the write stage: prompt construction and injection
  safety, tones and writing options, streaming, citation checks, marker
  rendering, and the reference list.

### Modified Capabilities

None.

## Impact

- New code: `src/wosarcher/stages/write.py`,
  `src/wosarcher/prompts/{write.md,passages.md,write_task.md,tones.toml}`,
  `tones()` in `src/wosarcher/prompts/__init__.py`, tests in
  `tests/stages/test_write.py`.
- Changed code: `models.py` (`Reference`, `Report` fields).
- Relies on core-contracts (`WritingOptions`, `LLM.stream`),
  research-collection (`prompts.load`, `Source`), passage-ranking
  (`Context`, `Passage`, `select.output_tokens`), provider-adapters (fake
  LLM with streaming).
- No new dependencies (`tomllib` is standard library); no change to
  `scripts/check_architecture.py`.
- docs/design.md sections implemented: Writing options, Citations,
  Prompt injection (writer). Changed: Writing options (tone names are
  checked against `tones.toml`; custom tones are new entries in that file),
  Citations (unknown numbers removed from the rendered report; reference
  list in first-citation order), Package layout (prompt file names).
