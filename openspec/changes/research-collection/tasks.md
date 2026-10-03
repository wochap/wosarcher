# Tasks

## 1. Setup

- [ ] 1.1 Add `markdown-it-py` to `pyproject.toml` dependencies and run `uv sync`; verify `uv run python -c "import markdown_it"` succeeds
- [ ] 1.2 In `scripts/check_architecture.py` add `"prompts": set()` and `"attachments": {"models", "config"}` to `ALLOWED`, add `"prompts"` to `PURE`, add `"prompts"` to the sets of `stages`, `runner`, `build`, `server`, `cli`, and `"attachments"` to the sets of `runner`, `build`, `server`, `cli`, with a comment giving the reason from design.md (Architecture table); verify `scripts/check` passes
- [ ] 1.3 Create `src/wosarcher/stages/__init__.py` with only a typed `noop` callback; verify `scripts/check` passes

## 2. Contracts and settings

- [ ] 2.1 In `models.py`, add or align `Sources`, `Query`, `Plan`, `Hit`, `Source`, `Page`, `Chunk`, `Attachment`, `Skipped`, `SearchResult`, `FetchResult`, `LoadResult`, `ChunkResult` exactly as in design.md (Contracts); update the searxng and firecrawl adapters and `adapters/fakes.py` if a field was renamed, and make `FirecrawlFetcher.fetch` set `truncated=True` when it cuts the markdown at `fetch.max_chars`; verify round-trip tests for each new type in `tests/test_models.py`, `tests/adapters/test_firecrawl.py::test_long_page_cut` asserting `truncated` is true, and that existing adapter tests still pass (spec: Page cap)
- [ ] 2.2 In `config.py`, add `PlanConfig` and `AttachConfig`, and align `ChunkConfig` (`size` 1000, `overlap` 100, `0 <= overlap < size`); add `plan` and `attach` to `Settings` (`FetchConfig.max_chars` already exists from provider-adapters; do not redefine it); verify tests in `tests/test_config.py` for the defaults (`plan.max_sub_queries` 3, `attach.max_bytes` 5000000, `chunk.size` 1000, `chunk.overlap` 100) and that `overlap >= size` fails naming `chunk.overlap`

## 3. Prompts

- [ ] 3.1 Create `src/wosarcher/prompts/__init__.py` with `load(name) -> string.Template` using `importlib.resources`; verify a test that `load("plan")` returns a template and that an unknown name raises an error naming it
- [ ] 3.2 Write `prompts/plan.md` (system message; placeholders `$query`, `$max_sub_queries`; asks for JSON `{"queries": [...]}`) and `prompts/plan_data.md` (fixed data preamble); verify a test that `load("plan").substitute(query="a $b", max_sub_queries=3)` keeps `a $b` literally

## 4. Search stage

- [ ] 4.1 Implement `merge_hits` in `stages/search.py`; verify tests: two queries finding the same normalised URL give one hit with both query IDs, lowest rank kept, first title kept (spec: URL dedupe, Tracking parameters)
- [ ] 4.2 Implement `search` with concurrent queries, `initial` merge, per-query failures as `Skipped`, and `on_item` calls; verify tests with the fake Searcher: two queries one page, one search raising, initial hits reused with `q0` (spec: Search over queries, Initial search)

## 5. Plan stage

- [ ] 5.1 Implement message building in `stages/plan.py`: system message from `plan.md`, data message from `plan_data.md` plus `<data>` block of at most 10 initial hits and the outlines, with `<data`/`</data` escaped; verify tests that a snippet containing `$query` and "ignore previous instructions" appears only in the data message, and that no page text is accepted as input (spec: Planner input)
- [ ] 5.2 Implement answer parsing (JSON object, then JSON list, else warning), trimming, case-insensitive dedupe including the main query, cap at `max_sub_queries`, and IDs `q1..qn`; verify tests: five returned and three kept, main query repeated in other case dropped, unreadable answer gives `q0` only plus one warning, IDs in order (spec: Planner output, Query identity)
- [ ] 5.3 Implement the `sources` rule: `files` or `max_sub_queries == 0` returns `q0` only without calling the LLM, `web` ignores outlines; verify tests with the fake LLM counting calls (spec: Sources setting)

## 6. Fetch stage

- [ ] 6.1 Implement `stages/fetch.py`: dedupe hits by normalised URL, semaphore of `concurrency`, copy `rank` and `query_ids` onto each page (no text cutting: the Fetcher applies `fetch.max_chars`), empty text and exceptions as `Skipped`, `on_item` for each page and failure; verify tests with the fake Fetcher: one page failing, empty page reason "empty content", max two in flight with ten hits, duplicate URL fetched once (spec: Fetch with failures, URL dedupe)

## 7. Attachments and load stage

- [ ] 7.1 Implement `attachments.collect` in `src/wosarcher/attachments.py` (files, sorted recursive directories skipping hidden parts, globs, suffix filter, size check before reading, no-match error); verify tests in `tests/test_attachments.py` with `tmp_path`: mixed directory skips `c.pdf` with a warning, oversized file skipped naming the limit, missing pattern raises naming it, hidden directory ignored (spec: Attachment paths)
- [ ] 7.2 Implement `load` in `stages/load.py` (UTF-8 with replacement, title from first H1 or name, content `source_id`, duplicate content skipped, pdf-ingest detection); verify tests: invalid bytes load with U+FFFD, same content twice gives one page and one duplicate, `<!-- page: 3 -->` marks `pdf-ingest` (spec: Attachment loading, pdf-ingest detection)
- [ ] 7.3 Implement `outline` in `stages/load.py` using `sections` from `stages/chunk.py`; verify a test that two headings with three lines each list both headings with only their first two lines, and that output is cut at 2000 characters (spec: Attachment outline)

## 8. Chunk stage

- [ ] 8.1 Implement `sections(text)` in `stages/chunk.py` with markdown-it-py; verify tests: nested `## Results` / `### Latency` gives path `["Results", "Latency"]`, text before the first heading has an empty path, `# ` inside a fenced block does not split (spec: Heading path, Split by headings)
- [ ] 8.2 Implement text cleaning (comments, `<img>`, images to alt, links to text, autolinks removed, whitespace collapse); verify tests: the link-and-image example gives `see the docs chart`, a comment is removed (spec: Stripped content)
- [ ] 8.3 Implement size windows with boundary search and overlap; verify tests: 2500 characters give three chunks of at most 1000 characters, each later chunk starts with text from the end of the previous, two 200-character sections give two chunks, empty sections give none (spec: Split by headings, then by size)
- [ ] 8.4 Implement pdf-ingest anchors with the marker approach (page in effect at chunk start, block IDs inside the chunk, anchors removed from text); verify a test with `<!-- page: 4 -->` and `<!-- a: p4-b1 -->` giving page ID `4` and block IDs `["p4-b1"]` (spec: pdf-ingest anchors)
- [ ] 8.5 Implement `chunk` with positions, `chunk_id`, and normalised-text dedupe across pages; verify tests: chunking one page alone or with others gives the same IDs, the same paragraph on two pages keeps the first and reports `duplicates == 1` (spec: Chunk identity and order, Near-duplicate removal)

## 9. Integration and docs

- [ ] 9.1 Add `tests/stages/test_collection_flow.py`: with fakes, run `load` → `search` (initial) → `plan` → `search` → `fetch` → `chunk` for a query with one attachment; verify every chunk has a source present in the pages and every web page's query IDs are a subset of the plan's IDs
- [ ] 9.2 Update docs/design.md: Pipeline (load runs before plan), Attachments (path expansion in `attachments.py`, page cap is for web pages only), Chunking (pdf-ingest anchors become `page_id`/`block_ids` and are removed from text), Package layout (`attachments.py`, `prompts/__init__.py`); verify the sections match the code
- [ ] 9.3 Verify `scripts/check --full` passes and `openspec validate research-collection --strict` passes
