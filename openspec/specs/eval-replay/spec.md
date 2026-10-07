# eval-replay Specification

## Purpose

Measures prefilter and scorer choices by replaying recorded runs from the
ranking stages with different settings, and keeps a recorded run that
proves the whole pipeline works end to end without live services.

## Requirements

### Requirement: Variants
The harness SHALL read named variants from a TOML file. Each variant SHALL
name the stage to fork from (`chunk`, `prefilter`, `score`, or `write`)
and a list of `--set` overrides. A variant with any other fork stage SHALL
be rejected with an error naming the variant and the allowed stages. A
`write` variant forks a run (a parent or an earlier fork) from `write`, so
the context is copied and only the report is written again; replaying it
implies `--write`.

#### Scenario: Valid variant
- **WHEN** the variants file defines `bm25` with `from = "score"` and `set = ["score.provider=bm25"]`
- **THEN** replaying with `bm25` forks each run from `score` with that override

#### Scenario: Chunk variant
- **WHEN** the variants file defines `chunk-current` with `from = "chunk"` and no overrides
- **THEN** replaying with it forks each run from `chunk`, makes no search or fetch request, and chunks the parent's pages again

#### Scenario: Write variant
- **WHEN** the variants file defines `write-current` with `from = "write"` and the replay names an earlier fork's run ID
- **THEN** the new fork copies that run's `context.json`, calls no searcher, fetcher, embedder, or scorer, and writes a report

#### Scenario: Invalid stage
- **WHEN** a variant sets `from = "fetch"`
- **THEN** the harness fails before forking and names the variant and the allowed stages `chunk`, `prefilter`, `score`, `write`

### Requirement: Replay
`python -m evals.replay` SHALL fork every given recorded run with every
chosen variant through `wosarcher fork <run_id> --from <stage> --until
select --json` plus the variant's overrides, and SHALL write one result
record per (run, variant) with the parent run ID, the variant, the fork's
run ID, and its status. With `--write` the forks SHALL run through the
write stage instead. A fork that fails SHALL be recorded as failed and the
replay SHALL continue. A (run, variant) pair that already has a result
SHALL be skipped unless `--force` is given.

A fork that ends `done` SHALL still be recorded as `failed` when its event
log shows that it did not measure the configured ranking:
- it has a `stage.failed` event for `score`, meaning the score stage fell
  back from the configured scorer. The error is then "score ran
  <provider> instead of <configured>: <first failure>";
- its prefilter `stage.done` provider method (the part before `:`) differs
  from its resolved `prefilter.provider`. The error is then "prefilter ran
  <method> instead of <configured>".

The fork's run ID and run directory SHALL still be recorded.

#### Scenario: Two variants
- **WHEN** replay runs over two recorded runs with variants `bm25` and `bm25-wide`
- **THEN** four forks are created and four result records are written

#### Scenario: Search and fetch held constant
- **WHEN** a run is replayed from `score`
- **THEN** the fork makes no search or fetch request and uses the parent's chunks

#### Scenario: Failed fork
- **WHEN** one variant's fork exits with a non-zero status (for example an invalid override)
- **THEN** that result is recorded with status `failed` and the fork's error text, and the other variants still run

#### Scenario: Scorer fell back
- **WHEN** a variant sets `score.provider=jev` without `score.fallback=[]`, Jev answers HTTP 404, and the fork ends `done` with `bm25`
- **THEN** the result has status `failed`, the fork's run ID, and an error starting "score ran bm25 instead of jev"

#### Scenario: Prefilter fell back
- **WHEN** a variant sets `prefilter.provider=embeddings`, the embedder is unreachable, and the fork's prefilter ran `bm25`
- **THEN** the result has status `failed` and the error "prefilter ran bm25 instead of embeddings"

#### Scenario: Small-input passthrough is not a fallback
- **WHEN** every query of a fork is small-input passthrough, so the score stage reports `passthrough` with no `stage.failed`
- **THEN** the result stays `done`

### Requirement: Metrics without an LLM
`python -m evals.metrics` SHALL compute, for every result record and
without calling any model: the number of selected passages, the context
size in characters and in estimated tokens (characters divided by 4,
rounded up), the seconds of each stage the fork ran (from its `stage.done`
events), and, for each pair of variants on the same parent run, the
Jaccard overlap of their selected chunk IDs. It SHALL print a Markdown
table per variant with medians and write the full metrics as JSON.

#### Scenario: Overlap
- **WHEN** variant A selects chunks {1, 2, 3} and variant B selects {2, 3, 4} from the same parent run
- **THEN** their overlap is 0.5

#### Scenario: Stage seconds
- **WHEN** a fork from `score` logged `stage.done` for score with 1.2 seconds
- **THEN** the metrics show score 1.2 seconds and no time for the copied stages

### Requirement: Judged precision
`python -m evals.judge` SHALL, only when run explicitly, judge each
result pointwise with the configured `llm`: one call per selected passage
asking whether it is relevant to the run's query, answered yes or no.
Precision is relevant passages divided by readable passages. Each call
SHALL send the query through the prompt template as the system message
and the whole passage text, never cut, in a separate user message, never
through a template, with effort `none` and temperature 0, whatever
`llm.reasoning` says. The answer is its first word, compared without
case; a passage whose answer is neither yes nor no is unreadable: it is
left out of the ratio and counted in the judgement's `unreadable`. A
result with no readable passage SHALL record precision as missing, not
zero. The calls of one result SHALL run concurrently within the LLM
block's concurrency limit. A provider error on any call of a result SHALL
record that result's precision and faithfulness as missing, print the
error on one line, and the judge SHALL go on; it SHALL never end with a
traceback. Judgements SHALL be saved so a second run does not call the
model again; `--force` SHALL judge again every result that already has a
judgement and replace its line.

`--samples N` (default 1) SHALL ask every item N times; an item's value
is its share of yes answers over its readable samples, and the ratios use
these values. The judgement SHALL record `samples`.

For every result whose fork finished `write`, the judge SHALL also judge
faithfulness: each citation in the report (every `[n]` group that is not a
link, with every number it holds) pairs its claim with passage `n`, and
one call per pair asks whether the passage supports the claim, or the
part of the claim the citation is attached to, yes or no, under the same
rules (template with the query only, claim and whole passage as data,
effort `none`, temperature 0, first-word answer, unreadable items). The
claim is the sentence that holds the citation: the report text from the
sentence boundary before the citation to the boundary after it. A
sentence boundary is `.`, `!`, or `?` followed by whitespace or the end of
the text, or a blank line, or the start or end of a list item, table row,
or heading line; a single line break inside a paragraph is not a
boundary, and a `.` followed by a letter or digit (as in `0.69` or
`gob.pe`) is not one. Every `[n]` marker except the judged citation's own
marker, Markdown emphasis and heading marks, list markers, and table
pipes SHALL be removed from the claim and its whitespace collapsed; the
judged marker stays as `[n]` so the judge can see which part of the
sentence it follows. Citations in one sentence share the sentence; a
claim is never empty when the sentence has any word. In a Markdown table
whose first row is a header, a citation in a body cell SHALL take as its
claim the row's first cell, the cell's column header, and the cell's own
text, joined as `<row label> — <column header>: <cell text>` with the
marker kept in the cell text; a citation in a header cell or in a table
without a header row SHALL take the row's cells joined by ` — `. Faithfulness SHALL
be recorded as supported pairs divided by readable pairs, and the number
of pairs SHALL be recorded as `citations`. A fork without a finished
report, a report with no citation, or a result with no readable pair
SHALL record faithfulness as missing, not zero. A citation number with no
passage in `context.json` SHALL be left out of the pairs.

#### Scenario: Precision
- **WHEN** a result has 4 selected passages and the judge answers yes for the first and third and no for the others
- **THEN** its precision is 0.5 and `unreadable` is 0

#### Scenario: Unparsable answer
- **WHEN** the judge answers "I cannot tell" for one of 4 passages and yes for the other three
- **THEN** that passage is unreadable, the precision is 1.0 over 3 readable passages, and `unreadable` is 1

#### Scenario: Malformed list
- **WHEN** the judge answers text that is neither yes nor no for every passage of a result
- **THEN** the result's precision is missing, the judge continues with the next result, and it exits 0

#### Scenario: Faithfulness
- **WHEN** a report holds the sentences "A is true [1]." and "B and C hold [2, 3]." and the judge answers yes, no, yes for the three pairs
- **THEN** the result records `citations` 3 and faithfulness 0.67 (2 of 3), with claims "A is true [1]", "B and C hold [2]", and "B and C hold [3]"

#### Scenario: Whole passage sent
- **WHEN** a selected passage has 1800 characters
- **THEN** the precision call and every faithfulness call for it carry all 1800 characters

#### Scenario: Attributed part marked
- **WHEN** a report sentence is "BM25 beats dense [2]; HyDE costs 40 ms [11]."
- **THEN** the pair for passage 11 has the claim "BM25 beats dense; HyDE costs 40 ms [11]" and the pair for passage 2 has "BM25 beats dense [2]; HyDE costs 40 ms"

#### Scenario: Decimal and domain inside a sentence
- **WHEN** a report sentence is "Hybrid reaches 0.7497 NDCG on gob.pe data [2], a 7.4% lift [3]."
- **THEN** the pair for passage 2 has the claim "Hybrid reaches 0.7497 NDCG on gob.pe data [2], a 7.4% lift"

#### Scenario: Adjacent citations
- **WHEN** a report sentence is "Both say so [1][2]."
- **THEN** the pairs have the claims "Both say so [1]" and "Both say so [2]"

#### Scenario: List item and table row
- **WHEN** a report holds the line "- **Costo:** gratuito [1]" and a table with the header "| Portal | Costo |" and the row "| CEJ | gratis [3] |"
- **THEN** the claims are "Costo: gratuito [1]" and "CEJ — Costo: gratis [3]"

#### Scenario: Several cited cells in one row
- **WHEN** a table has the header "| Tool | Role | License | Status |" and the row "| Jellyfin | Watch | GPL [13] | Active [38] |"
- **THEN** the pairs have the claims "Jellyfin — License: GPL [13]" and "Jellyfin — Status: Active [38]"

#### Scenario: Table without a header row
- **WHEN** a table's first row is "| CEJ | gratis [3] |" and no separator row follows it
- **THEN** the claim is "CEJ — gratis [3]"

#### Scenario: Line break inside a paragraph
- **WHEN** a report paragraph is "The CEJ changed\nits form in 2026 [4]."
- **THEN** the claim is "The CEJ changed its form in 2026 [4]"

#### Scenario: Replayed without --write
- **WHEN** a result's fork stopped at `select` and has no `report.json`
- **THEN** its precision is judged and its faithfulness is missing

#### Scenario: Report without citations
- **WHEN** a result's report cites no passage
- **THEN** its faithfulness is missing and `citations` is 0

#### Scenario: Unparsable faithfulness answer
- **WHEN** the faithfulness judge answers neither yes nor no for every pair
- **THEN** the result's faithfulness is missing, its precision is kept, and the judge continues

#### Scenario: Claims and passages as data
- **WHEN** the faithfulness judge is called for a pair
- **THEN** the system message holds only the template with the query, and the user message holds that claim and passage

#### Scenario: Judge sends no thinking
- **WHEN** the judge calls the LLM
- **THEN** the request body has `reasoning_effort: "none"`, `temperature: 0`, and a token cap equal to the judge's limit

#### Scenario: Provider error on one result
- **WHEN** the endpoint answers 502 for one passage call of the first result
- **THEN** that result records precision and faithfulness as missing, the error is printed on one line, the next result is judged, and the judge exits 0

#### Scenario: Samples averaged
- **WHEN** `--samples 3` and a passage is answered yes, yes, no
- **THEN** its value is 0.67, the judgement records `samples` 3

#### Scenario: Force re-judges
- **WHEN** a result already has a judgement and the judge runs with `--force`
- **THEN** the result is judged again and `judgements.jsonl` holds one line for it, the new one

#### Scenario: Concurrent calls
- **WHEN** a result has 30 passages and `llm.concurrency` is 4
- **THEN** at most 4 judge calls are in flight at once and all 30 are made

### Requirement: Judged coverage
`python -m evals.judge` SHALL judge, for every result, whether the run
covers each part of its question.

Question parts: for each parent run ID, the judge SHALL make one LLM call
that turns the run's query (from `context.json`) into a numbered list of
parts, the distinct things the question asks for. Only the query SHALL go
through the parts prompt template; the call SHALL use effort `none` and
temperature 0. The answer SHALL be a JSON list of strings, optionally
inside a Markdown code fence; blank items SHALL be dropped and at most the
first 20 kept. An answer that is not such a list, or a list with no item
left, is unparsable. Parsed parts SHALL be saved in `<DIR>/parts.jsonl`,
one line per parent run ID with `parent_run_id`, `query`, and `parts`, and
every later result of the same parent, in this or any later judge call,
including with `--force`, SHALL use the saved parts without calling the
model. Unparsable parts and a provider error on the parts call SHALL save
nothing.

For each part the judge SHALL ask two pointwise yes/no questions with the
same rules as precision (template with the query only, data in a separate
user message never through a template, effort `none`, temperature 0,
first-word answer, unreadable items, `--samples`, concurrent calls):

- `coverage`: the user message holds the part and the report's rendered
  Markdown (`report.json` `markdown`, never cut); the answer is yes when
  the report answers that part.
- `retrievable`: the user message holds the part and the text of every
  selected passage in `context.json`, each with its number, never cut; the
  answer is yes when the passages hold enough to answer that part.

Each metric SHALL be its yes items divided by its readable items, and the
judgement SHALL record `parts` (the number of parts), `coverage`, and
`retrievable`; unreadable coverage and retrievable items SHALL count in
`unreadable`. A result without `report.json` SHALL record coverage as
missing and still judge retrievable. Unparsable parts SHALL record parts 0
and both metrics missing, print one line, and the judge SHALL go on. A
metric with no readable item SHALL be missing, not zero. A provider error
on any call of a result SHALL record precision, faithfulness, coverage, and
retrievable as missing, as for precision.

#### Scenario: Parts cached per parent
- **WHEN** two results share a parent run ID and the judge runs over both, then runs again with `--force`
- **THEN** the parts call is made once, `parts.jsonl` holds one line for that parent, and both results are judged against the same parts

#### Scenario: Coverage
- **WHEN** a result's query yields 4 parts and the coverage judge answers yes for 2 of them and no for the others
- **THEN** its coverage is 0.5 and `parts` is 4

#### Scenario: Retrievable judged from passages only
- **WHEN** the retrievable judge is called for a part of a result with 3 selected passages
- **THEN** the system message holds only the template with the query, and the user message holds the part and the 3 passage texts with their numbers and no report text

#### Scenario: Missing report
- **WHEN** a result's fork stopped at `select` and has no `report.json`
- **THEN** its coverage is missing, its retrievable is judged, and no coverage call is made

#### Scenario: Unparsable parts list
- **WHEN** the parts call answers "The question asks about several things."
- **THEN** the result records `parts` 0 with coverage and retrievable missing, its precision and faithfulness are still judged, nothing is written to `parts.jsonl`, and the judge exits 0

#### Scenario: Parts capped
- **WHEN** the parts call answers a JSON list of 26 strings
- **THEN** the first 20 are saved and judged

#### Scenario: Fenced list
- **WHEN** the parts call answers a JSON list inside a ```` ```json ```` code fence
- **THEN** the list is parsed

### Requirement: Judged items
`python -m evals.judge` SHALL append one line per judged item to
`<DIR>/items.jsonl`: `run_id`, `variant`, `kind` (`precision`,
`faithfulness`, `coverage`, or `retrievable`), `index` (the item's
position in its kind for that run), `n` (the passage's citation number;
for `coverage` and `retrievable`, the part's number starting at 1),
`claim` (the sentence, faithfulness only, else null), `part` (the part
text, coverage and retrievable only, else null), `passage` (the text as
sent to the judge for precision and faithfulness; empty for coverage and
retrievable), `value` (1, 0, or null when unreadable), and `answer` (the
first sample's answer text, at most 80 characters). With `--samples N` the
value is the averaged value. `--force` SHALL remove the re-judged runs'
item lines before appending the new ones. A result recorded as missing
because of a provider error SHALL write no item lines.

`python -m evals.items --results DIR [--run ID] [--failed]` SHALL print
the items of `<DIR>/items.jsonl` as Markdown without any model call: one
section per run (`variant · run_id`), faithfulness items first, then
coverage, retrievable, and precision. A faithfulness or precision item
SHALL show its value, `n`, the claim when present, and the first 300
characters of the passage; a coverage or retrievable item SHALL show its
kind, value, part number, and part text. `--failed` SHALL print only items
whose value is below 1; `--run` only one run. A missing items file SHALL
print nothing and exit 0.

#### Scenario: Items written
- **WHEN** a result with 3 passages, 2 claim pairs, and 2 question parts is judged with a report
- **THEN** `items.jsonl` gains 3 `precision` lines, 2 `faithfulness` lines, 2 `coverage` lines, and 2 `retrievable` lines for its run ID; the coverage and retrievable lines carry `part`, `n` 1 and 2, and an empty `passage`

#### Scenario: Unreadable item
- **WHEN** the judge answers "unclear" for a passage
- **THEN** that item's line has `value` null and `answer` "unclear"

#### Scenario: Force replaces items
- **WHEN** a run with 5 item lines is judged again with `--force`
- **THEN** `items.jsonl` holds only the new lines for that run

#### Scenario: Failed pairs listed
- **WHEN** `python -m evals.items --results DIR --failed` runs over a run with one unsupported pair and four supported ones
- **THEN** the output shows one faithfulness item for that run, with its claim and passage excerpt, and no supported item

#### Scenario: Failed parts listed
- **WHEN** `python -m evals.items --results DIR --failed` runs over a run whose part 2 is judged 0 for coverage and 1 for retrievable
- **THEN** the output shows one coverage item with part number 2 and its text, and no retrievable item for that part

### Requirement: Recorded-run fixture
The repository SHALL contain, tracked in version control, a small recorded
run directory produced by `wosarcher run` from recorded SearXNG, Firecrawl,
and LLM responses, with every artifact of a finished run, and a script that
regenerates it from those responses. The fixture SHALL contain no absolute
path of the machine that generated it. Every artifact in the fixture SHALL
parse with the current contract models, and the tests that use it SHALL
pass on a fresh clone without regenerating it.

#### Scenario: Fixture parses
- **WHEN** the test suite loads every artifact and event of the fixture run
- **THEN** each one parses with its contract model

#### Scenario: Fixture forks
- **WHEN** the fixture run is copied to a temporary runs directory and forked from `score` with `score.provider=bm25`
- **THEN** the fork finishes `select` without any network request

#### Scenario: Fresh clone
- **WHEN** the repository is cloned and `git ls-files tests/fixtures/runs` is run
- **THEN** every file of `tests/fixtures/runs/20260101-000000-fixture/` is listed

#### Scenario: No machine paths
- **WHEN** the fixture is regenerated in a temporary directory
- **THEN** no fixture file contains that temporary directory's path

### Requirement: End-to-end run without live services
An automated test SHALL run `wosarcher run` with the real SearXNG,
Firecrawl, and LLM adapters against the recorded responses (no network),
with BM25 as prefilter and scorer, and SHALL check that the run finishes,
that every artifact exists, that event `seq` values have no gaps, and that
every citation in the report refers to a selected passage. No test SHALL
require a live service.

#### Scenario: Full run with recorded responses
- **WHEN** the end-to-end test runs `wosarcher run "q" --profile e2e`
- **THEN** the run ends with `run.done`, `report.md` cites only passage numbers present in `context.json`, and no request left the process

#### Scenario: Unexpected request
- **WHEN** the pipeline sends a request that has no recorded response
- **THEN** the test fails naming the URL
