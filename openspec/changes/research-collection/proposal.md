# Proposal

## Why

The contracts, BM25, and adapters exist, but nothing turns a query and a
set of attachments into the chunks that ranking needs. This change adds the
collection half of the pipeline as pure stages: plan the research, find
and fetch web pages, load attached files, and cut everything into
deduplicated, citable chunks. Ranking (passage-ranking) and writing
(report-writing) build on its output.

## What Changes

- Stages in `src/wosarcher/stages/`, one file each, all pure (inputs and
  ports in, a model out; no files, no events):
  - `search.py`: runs the Searcher for a list of queries concurrently,
    merges hits by normalised URL, and records every query ID that found a
    hit. Also used for the initial search with the main query.
  - `plan.py`: the planner. One LLM call writes sub-queries from the main
    query, the initial search titles and snippets, and attachment
    outlines. Fetched page content never reaches it. With `--sources
    files` it makes no LLM call and plans only the main query.
  - `fetch.py`: fetches each unique hit URL once, with a concurrency
    limit; a failed page is recorded with a reason and the stage
    continues. The page cap (`fetch.max_chars`) stays in the fetch
    adapter, which now also marks cut pages as truncated.
  - `load.py`: turns attachment bytes into pages: UTF-8 with replacement,
    title, content identity, duplicate content dropped, pdf-ingest
    markdown detected by its page and anchor comments; plus an outline of
    each attachment for the planner.
  - `chunk.py`: markdown-aware chunking by headings, then by size
    (`chunk.size` 1000, `chunk.overlap` 100); heading path, pdf-ingest
    page and block IDs kept; HTML comments, image payloads, and link URLs
    stripped; near-duplicate chunks dropped by normalised-text hash.
- `src/wosarcher/attachments.py`: expands `--attach` paths (files,
  directories, globs), skips unsupported or oversized files with a
  warning, and reads the bytes. It is the only file I/O in this change and
  sits outside `stages/` so stages stay pure.
- `src/wosarcher/prompts/`: `plan.md` and `plan_data.md`, plus a small
  loader that reads prompt files from package data and fills them with
  `string.Template` from trusted values only.
- Contracts and settings this change needs: `Plan`, `Outline` text,
  `Attachment`, `Skipped`, result models for search, fetch, load, and
  chunk; fields on `Hit`, `Page`, and `Chunk`; settings `plan`,
  `attach`, `chunk.size`, `chunk.overlap`.
- New dependency: `markdown-it-py` (heading tree for chunking).

## Non-goals

- No ranking, prefilter, selection, or writing (passage-ranking,
  report-writing).
- No runner, run directory, events, caches, or CLI flags (`--attach` and
  `--sources` are wired by run-orchestration).
- No local PDF parsing, no formats other than `.md` and `.txt`.
- No recursive (deep) research; one planning round.
- No retry of failed pages beyond what the HTTP client already does.

## Capabilities

### New Capabilities

- `research-planning`: the initial search and the planner: what the
  planner sees, what it returns, and how `--sources` changes it.
- `source-collection`: search over sub-queries, URL dedupe and query IDs,
  fetch with per-page failures and the page cap, and loading attachments
  (paths, formats, size limit, encoding, pdf-ingest detection).
- `chunking`: markdown-aware chunking, kept metadata, stripped content,
  and near-duplicate removal.

### Modified Capabilities

None.

## Impact

- New code: `src/wosarcher/stages/{__init__,search,plan,fetch,load,chunk}.py`,
  `src/wosarcher/attachments.py`, `src/wosarcher/prompts/{__init__.py,plan.md,plan_data.md}`,
  tests under `tests/stages/` and `tests/test_attachments.py`.
- Changed code: `models.py` (new and extended contracts), `config.py`
  (`PlanConfig`, `AttachConfig`, `ChunkConfig`), `adapters/firecrawl.py`
  (sets `Page.truncated`),
  `pyproject.toml` (markdown-it-py).
- `scripts/check_architecture.py`: adds the parts `prompts` (pure: reads
  read-only package data, imports nothing from the package) and
  `attachments` (file I/O for user paths, imports `models` and `config`);
  `stages` may import `prompts`; `runner`, `build`, `server`, and `cli` may
  import both. Reason: stages must stay pure, yet prompts must live in
  files and attachment paths must be read from disk somewhere.
- Relies on core-contracts (models, ports, config), lexical-bm25 (not used
  here), and provider-adapters (fakes for Searcher, Fetcher, LLM).
- docs/design.md sections implemented: Pipeline (plan, search, fetch,
  load, chunk), Initial search, Dedupe, Attachments, Chunking, Prompt
  injection (planner). Changed: Pipeline (load runs before plan so the
  planner can see outlines), Attachments (path expansion lives in
  `attachments.py`; the page cap applies to web pages only), Chunking
  (pdf-ingest anchors become chunk metadata), Package layout
  (`attachments.py`, `prompts/__init__.py`).
