# Tasks

## 1. Contracts and prompts

- [ ] 1.1 In `models.py`, add `Reference` and set `Report` fields (`body`, `markdown`, `cited`, `references`, `warnings`) as in design.md (Contracts); verify round-trip tests in `tests/test_models.py`
- [ ] 1.2 Create `src/wosarcher/prompts/tones.toml` with the 11 tones and gpt-researcher descriptions, and add `tones() -> dict[str, str]` to `prompts/__init__.py` (tomllib, lowercase keys); verify a test that `tones()` has exactly the 11 names and that `tones()["critical"]` equals the gpt-researcher text (spec: Tones)
- [ ] 1.3 Write `prompts/write.md` (`$query`, `$tone`, `$tone_description`, `$tone_instructions`, `$words`, `$language`), `prompts/passages.md` (no placeholders), and `prompts/write_task.md` (`$query`, `$words`, `$language`); verify a test that each loads with `prompts.load` and substitutes the listed names without `KeyError`

## 2. Messages

- [ ] 2.1 Implement `messages` in `stages/write.py` (system, passages, task) with passage labels and delimiter escaping; verify tests: an injection passage appears only inside the `<passages>` block, a passage containing `</passages>` leaves exactly one closing delimiter, passage 3 is labelled `[3] Paper — Results › Latency`, a pdf-ingest passage uses `p. 12` (spec: Passages are data, Passage labels)
- [ ] 2.2 Implement tone lookup and option text; verify tests: tone `Critical` puts its description in the system message, `tone_instructions` appears in the system message, 600 words in German appear in the system message (spec: Tones, Length and language)

## 3. Writing and streaming

- [ ] 3.1 Implement `write`: validate tone and reference style first, raise on empty context, stream with `max_tokens=output_tokens(words)`, call `on_delta` per piece; verify tests with the fake LLM: three pieces arrive in order and the body is their concatenation; 600 words gives `max_tokens == 1200`; tone `humorous` and style `Harvard` fail with no LLM call and list the known names (spec: Streaming, Length and language, Unknown tone, Unknown style)

## 4. Citations and rendering

- [ ] 4.1 Implement `citations` and the known-number check; verify tests: `[7]` and `[2, 9]` with passages 1..5 give warnings for 7 and 9; `[1](https://x)` is not a citation; a body with no citation gets the "cites no passage" warning (spec: Citation check)
- [ ] 4.2 Implement marker rendering for `numeric`, `superscript`, and `author-year`; verify tests: `[2, 9]` renders `[2]` and `[7]` is removed; `[1, 2]` renders `<sup>1,2</sup>`; two passages from `www.example.org` without author or date render `(example.org, n.d.)`; `body` keeps the raw markers (spec: Citation markers)
- [ ] 4.3 Implement reference formatting for APA, MLA, Chicago, IEEE with passage locators; verify tests: the APA web example string from the spec, IEEE entries numbered `[1]`, `[2]` by first citation, a pdf-ingest passage listed as `[4] p. 12 (p12-b3)`, one expected string per style for a file source (spec: Reference list)
- [ ] 4.4 Implement `render` (rendered body plus `## References`, `cited`, `references`, `warnings`); verify a test that a report citing passages from two sources lists each source once in first-citation order with its passage numbers ascending (spec: Reference list)

## 5. Docs and checks

- [ ] 5.1 Update docs/design.md: Writing options (tones checked against `prompts/tones.toml`; a custom tone is a new entry), Citations (unknown numbers removed from the rendered report, reference list in first-citation order, `Report.body` keeps raw markers), Package layout (`prompts/` holds `jev.toml`, `plan.md`, `plan_data.md`, `write.md`, `passages.md`, `write_task.md`, `tones.toml`); verify the sections match the code
- [ ] 5.2 Verify `scripts/check --full` passes and `openspec validate report-writing --strict` passes
