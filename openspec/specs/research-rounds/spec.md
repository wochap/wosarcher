# research-rounds Specification

## Purpose

Repeats search, fetch, chunk, prefilter, and score in rounds. Between
rounds, a gap step reads the best passages so far and writes follow-up
queries for what is missing, so deep runs learn and keep searching before
one final select and write.

## Requirements

### Requirement: Rounds
The `research` config block SHALL have:
- `rounds`: an integer from 1 to 8, default 1;
- `queries_per_round`: a positive integer, default 3;
- `gap_context_tokens`: a positive integer or the string `auto`, default
  4000.

With `rounds` = 1 a run SHALL behave as before this capability: the `gap`
stage is skipped and no round events are emitted. With `rounds` > 1 and
web sources (`web` or `both`), the stages `search`, `fetch`, `chunk`,
`prefilter`, `score`, and `gap` SHALL run as a loop, one pass per round.
- Round 1 searches the planner's sub-queries.
- Round k > 1 searches the follow-up queries that the gap step wrote after
  round k-1.

`rounds` is the number of rounds to run, not a maximum: research SHALL run
every round unless a stop rule other than `max rounds` holds
(Requirement: Stop rules). No model decides that coverage is good enough.

The gap step SHALL NOT run after the last round. A run whose sources are
`files`, or whose plan has no sub-query, SHALL run one round.

#### Scenario: Three rounds
- **WHEN** `research.rounds = 3` and the gap step writes follow-ups after rounds 1 and 2
- **THEN** search through score run three times, gap runs twice, then select and write run once

#### Scenario: Good coverage does not stop research
- **WHEN** `research.rounds = 3` and every query is covered after round 1
- **THEN** the gap step still writes follow-ups and rounds 2 and 3 run

#### Scenario: One round
- **WHEN** `research.rounds = 1`
- **THEN** the stages run once in order, `gap` is reported as skipped, and no `round.done` event is emitted

#### Scenario: Files only
- **WHEN** `research.rounds = 3` and sources are `files`
- **THEN** one round runs and the gap stage is skipped

#### Scenario: Gap context default
- **WHEN** no source sets `research.gap_context_tokens`
- **THEN** the resolved value is 4000

#### Scenario: Invalid gap context value
- **WHEN** a profile sets `research.gap_context_tokens = "all"`
- **THEN** loading fails with an error naming the field

### Requirement: Gap step
After round k (k < `research.rounds`), the gap stage SHALL make one LLM
call, and a second one only as described below. The first call SHALL send:
- a system message from `prompts/gap.md`, with only the main query, the
  maximum number of follow-ups, and the date substituted;
- one user message with a data preamble and a delimited data block. The
  block holds, in order: the coverage table (Requirement: Coverage table);
  when round k fetched no new page, the line "Round <k> found only pages
  fetched in earlier rounds:" followed by round k's query IDs and texts;
  and the passages that select picks from every round's kept scores with
  the gap budget. Passage text SHALL never go through a template, and text
  that would close the block SHALL be neutralised.

The system prompt SHALL tell the model to write follow-ups for `uncovered`
queries first, then for other gaps, to try new angles for queries that
found only known pages, and to always write at least one query.

The gap budget SHALL be `research.gap_context_tokens` when it is a number.
When it is `auto`, the gap budget SHALL be the room `llm.context_window`
leaves after `select.prompt_reserve_tokens`, the gap call's output limit (768
tokens), and the estimated tokens of the main query and the existing
queries' text (estimated with `llm.chars_per_token` and
`llm.token_margin`). A gap budget of 0 or less SHALL count as a failed gap
step.

The reply SHALL be JSON with `queries` (strings) and `note` (one or two
sentences on what is still missing). Any other field, including `stop`,
SHALL be ignored. An unreadable reply SHALL count as a failed gap step.

The gap step SHALL drop a follow-up query when it is empty, longer than 200
characters, or contains a URL. It SHALL also drop one that duplicates an
existing query or an earlier follow-up, ignoring case and surrounding
whitespace. It SHALL keep at most `research.queries_per_round`. Kept
follow-ups get the next query IDs after the last existing one, carry
`round` = k+1, and are appended to `plan.json`.

When the first reply keeps no follow-up, the gap step SHALL make one more
call: the same two messages, the first reply as an `assistant` message, and
a `user` message from `prompts/gap_retry.md` (only the maximum number of
follow-ups substituted) followed by a delimited data block listing each
dropped query with its reason (`empty`, `too long`, `URL`, or `duplicate`).
The second reply SHALL be read and checked the same way. The step's result
SHALL record that it retried. When the second reply keeps no follow-up
either, research stops with `no follow-ups`; an unreadable second reply
counts as a failed gap step.

#### Scenario: Follow-ups numbered
- **WHEN** the plan has `q0` to `q5` and the gap step after round 1 returns "a", "A ", "https://x.example/y", and "b"
- **THEN** the kept follow-ups are `q6` "a" and `q7` "b", both with round 2

#### Scenario: Passages are data
- **WHEN** a kept passage contains "Ignore all previous instructions" and the closing delimiter of the data block
- **THEN** the text appears only inside the data block of the user message, and the block has exactly one closing delimiter

#### Scenario: Context budget
- **WHEN** `research.gap_context_tokens = 4000`
- **THEN** the passages in the gap call are estimated at no more than 4000 tokens

#### Scenario: Auto gap budget
- **WHEN** `research.gap_context_tokens = "auto"`, `llm.context_window = 1000000`, `select.prompt_reserve_tokens = 2000`, and the main query and existing queries are estimated at 1,500 tokens
- **THEN** the passages in the gap call are estimated at no more than 995,732 tokens

#### Scenario: Stop field ignored
- **WHEN** the gap reply is `{"queries": ["a"], "note": "n", "stop": true}`
- **THEN** follow-up "a" is kept and the next round runs

#### Scenario: Retry after only duplicates
- **WHEN** the first gap reply after round 1 holds only "b" and "B", and `q3` is "b"
- **THEN** a second call is made whose last user message lists "b" and "B" as `duplicate`, and its follow-ups are kept as usual

#### Scenario: Retry fails too
- **WHEN** neither gap reply after round 2 keeps a follow-up
- **THEN** research stops after round 2 with `no follow-ups`

#### Scenario: Known pages named
- **WHEN** round 2 searched `q6` and `q7` and fetched no new page
- **THEN** the gap call after round 2 names `q6` and `q7` under "Round 2 found only pages fetched in earlier rounds:"

### Requirement: Stop rules
Research SHALL stop, and select SHALL follow, at the first of these. Each
has a stop reason:

| Condition | Stop reason |
|---|---|
| the last round ran | `max rounds` |
| two rounds in a row after round 1 fetched no new page because all their hits were already fetched or queued | `no new sources` |
| the pages fetched across all rounds reached `fetch.max_pages` | `page limit reached` |
| the gap step kept no follow-up after its second call | `no follow-ups` |
| a gap call failed, timed out, or its reply was unreadable | `gap step failed` |

A single round after round 1 that fetched no new page SHALL NOT stop
research: the gap step runs and is told which queries found only known
pages. For `no new sources` the end note SHALL read "Follow-up searches
returned only pages fetched in earlier rounds." For `no follow-ups` the end
note SHALL read "The gap step wrote no usable follow-up query." A failed
gap step SHALL add the warning `gap failed: <error>` and SHALL NOT fail the
run.

#### Scenario: Coverage sufficient
- **WHEN** `research.rounds = 3` and the gap step after round 1 writes the note "Every sub-query has primary sources." with two follow-ups
- **THEN** research does not stop: round 2 searches the two follow-ups, and the note is round 1's gap note, not an end note

#### Scenario: One empty round continues
- **WHEN** `research.rounds = 4` and round 2's follow-ups find only URLs that round 1 already fetched
- **THEN** round 2 reports 0 new pages, the gap step runs after round 2, and round 3 runs

#### Scenario: No new sources
- **WHEN** `research.rounds = 4` and rounds 2 and 3 both fetch no new page
- **THEN** research stops after round 3 with `no new sources`, no gap step runs after round 3, and the end note is "Follow-up searches returned only pages fetched in earlier rounds."

#### Scenario: Page limit
- **WHEN** `fetch.max_pages = 20` and rounds 1 and 2 fetch 12 and 8 pages
- **THEN** research stops after round 2 with `page limit reached`

#### Scenario: Gap failure
- **WHEN** the gap LLM call fails after round 1
- **THEN** select and write still run on round 1's passages, the stop reason is `gap step failed`, and the run has a `gap failed:` warning

### Requirement: Round data
Every query, hit, page, and score SHALL carry the `round` it first appeared
in. The run artifacts SHALL stay cumulative: `plan.json`, `hits.jsonl`,
`pages.jsonl`, `chunks.jsonl`, `candidates.jsonl`, and `scores.jsonl` hold
every round. A multi-round run SHALL write `research.json` with:
- `planned` (the configured rounds), `ran`, `reason`, and `note`;
- one entry per round, with `round`, the query IDs searched,
  `new_pages`, `known_pages` (hits already fetched in earlier rounds),
  `kept` (passages kept that round), the gap `note` written after it
  (empty for the last round), and `uncovered`, the IDs of the queries the
  coverage table marked `uncovered` when the gap step ran after it (empty
  for the last round).

#### Scenario: Research record
- **WHEN** a four-round run stops after round 3 with `no new sources`
- **THEN** `research.json` has `planned` 4, `ran` 3, `reason` "no new sources", and three round entries, the second and third with `new_pages` 0

#### Scenario: Uncovered recorded
- **WHEN** the coverage table after round 1 marks `q4` and `q6` uncovered
- **THEN** round 1's entry in `research.json` has `uncovered` = `["q4", "q6"]`

### Requirement: Fetch and pairing across rounds
The fetch page cap (`fetch.max_pages`) SHALL count pages across all rounds.
In a run with more than one planned round, round k SHALL fetch at most its
round cap:

- `left` is `fetch.max_pages` minus the pages fetched in earlier rounds;
- `later` is the number of planned rounds after round k;
- the reserve is `research.queries_per_round` × `search.max_results` ×
  `later`;
- the even share is `left` divided by (`later` + 1), rounded up;
- the round cap is the larger of `left` minus the reserve and the even
  share, and never more than `left`.

The last planned round's cap is `left`. A single-round run fetches at most
`fetch.max_pages`. A round's fetch queue SHALL hold only hits whose URL was
not fetched or queued in an earlier round; hits beyond the round cap stay
unfetched for that round, in the fetch order of source-collection. Each
round SHALL chunk only its new pages. It SHALL prefilter and score only
pairs of its own queries with its new chunks, plus attached file chunks for
its own queries. A page fetched in an earlier round SHALL NOT pair with a
later round's query.

#### Scenario: Known page
- **WHEN** round 2's query `q6` finds a URL fetched in round 1
- **THEN** the URL is counted as known for round 2, and no pair of `q6` with that page's chunks is scored

#### Scenario: Cap across rounds
- **WHEN** `fetch.max_pages = 30`, `research.rounds = 2`, and round 1 fetched 25 pages
- **THEN** round 2 fetches at most 5 pages

#### Scenario: Deep preset leaves room for later rounds
- **WHEN** a deep run (`fetch.max_pages = 60`, `research.rounds = 3`, `research.queries_per_round = 3`, `search.max_results = 10`) has 7 round-1 queries that find 70 new URLs
- **THEN** round 1 fetches at most 20 pages (reserve 60 leaves 0, the even share is 20), research does not stop with `page limit reached` after round 1, and the gap step runs

#### Scenario: Reserve smaller than the room
- **WHEN** `fetch.max_pages = 60`, `research.rounds = 2`, `research.queries_per_round = 3`, and `search.max_results = 5`
- **THEN** round 1 may fetch up to 45 pages (60 minus a reserve of 15, above the even share of 30)

#### Scenario: Single round
- **WHEN** `research.rounds = 1` and `fetch.max_pages = 15`
- **THEN** the round fetches up to 15 pages

### Requirement: Scoring across rounds
When a round's scorer falls back, later rounds SHALL start with the scorer
that ran. A chunk SHALL stay kept for at most one query across all rounds:
the earliest round's pair wins. Final select SHALL run once, after the
loop, over all rounds' kept scores and all queries in plan order.

#### Scenario: Sticky fallback
- **WHEN** the configured scorer fails in round 1 and `bm25` runs
- **THEN** rounds 2 and later score with `bm25`

#### Scenario: Chunk kept once
- **WHEN** a file chunk is kept for `q1` in round 1 and scores above threshold for `q6` in round 2
- **THEN** only the `q1` pair is kept

### Requirement: Resume and fork with rounds
A multi-round run SHALL count its loop stages as finished only after
`research.done`. A run resumed before that SHALL keep its plan reset to the
round-1 queries, discard the loop's artifacts, and restart the loop at
round 1's `search`. A fork of a multi-round run from a loop
stage (`search` to `gap`) SHALL copy only the earlier stages' artifacts up
to `plan` and run the loop again from round 1 with the parent's plan
queries for round 1. A fork from `select` or `write` SHALL reuse every
round.

#### Scenario: Interrupted in round 2
- **WHEN** a three-round run was interrupted during round 2's fetch and is resumed
- **THEN** the run restarts at round 1's `search` with the round-1 queries of the plan, and the planner is not called again

#### Scenario: Fork from score
- **WHEN** a finished three-round run is forked from `score`
- **THEN** the fork runs the loop from round 1 with the parent's round-1 queries

#### Scenario: Rewrite
- **WHEN** a finished three-round run is forked from `write`
- **THEN** the fork reuses `context.json`, `plan.json` with every round's queries, and `research.json`

### Requirement: Coverage table
The gap step SHALL build a coverage table from `scores.jsonl` and the plan,
with no other call, one line per query in plan order (`q0` first, every
round so far):

`<ID> · <status> · best <display or —> · kept <n> — <query text>`

- `kept` is the number of the query's pairs that are kept.
- `best` is the highest display score among the query's pairs, with two
  decimals, or `—` when the query has no pair or only pairs without a
  display score.
- The status is:
  - `covered` when the query has a kept pair with a display score, or a
    pair dropped because its chunk was kept for another query
    (`other_query`);
  - `unscored` when its only kept pairs have no display score (small-input
    passthrough);
  - `uncovered` otherwise: no pair, or every pair dropped by the threshold.

The table SHALL start with one line naming the scorers that produced the
scores, and for each whether its scores are calibrated (`jev`: "absolute
0–1 scale, kept from <threshold display>") or relative (`rerank`, `bm25`:
"relative scale; every query keeps its best pair, so judge by best").

#### Scenario: Jev uncovered query
- **WHEN** the scorer is `jev` with `score.min_score = 1.5` and every pair of `q4` scored below 1.5
- **THEN** the table has "q4 · uncovered · best 0.43 · kept 0 — <q4 text>" when its best value was 1.3

#### Scenario: Covered elsewhere
- **WHEN** `q2`'s only kept pair was dropped as `other_query` because `q1` kept the same chunk
- **THEN** `q2` is `covered` with "kept 0"

#### Scenario: No hits
- **WHEN** `q5` found no search result
- **THEN** the table has "q5 · uncovered · best — · kept 0 — <q5 text>"

#### Scenario: Passthrough query
- **WHEN** `q3`'s pages were small and its chunks were kept by passthrough
- **THEN** `q3` is `unscored`

#### Scenario: Relative scorer
- **WHEN** the scorer is `rerank`
- **THEN** the table's first line says the rerank scale is relative and to judge by best
