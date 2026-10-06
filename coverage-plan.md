# Plan: coverage judge, then draft-driven gap step

Handoff for the agent that proposes and implements these two changes
(`/opsx:propose coverage-judge`, then `/opsx:propose draft-driven-gap`,
each followed by `openspec-pipeline --on-input auto --apply-effort low
--gate scripts/check <change>`). Written 2026-10-06 after a session that
tuned retrieval and the writer. Read `docs/design.md` (Pipeline, Research
rounds, Evals), `openspec/specs/research-rounds/spec.md` (Gap step,
Coverage table, Stop rules), `openspec/specs/eval-replay/spec.md`, and
`evals/judge.py` before writing artifacts. Delete this file once both
changes are proposed.

## Where the pipeline stands

Landed on `main` this session, all measured with the eval harness:

- Every web chunk pairs with every query (`cross-query-pairing`,
  `pairing-all-only`); scored text is `title > heading path` plus body
  (`scoring-context-headers`); Jev threshold 2.0 with a best-pair floor
  (`calibrated-floor`, `jev-threshold-default`); boilerplate per block
  (`boilerplate-blocks`).
- Writer: grounding rules in `prompts/write.md` and `answer.md`
  (`writer-grounding`); per-step thinking `llm.reasoning.plan|gap|write`
  (`llm-reasoning-control`, `thinking-token-cap`). The user's deployment
  sets `reasoning.write = "low"` for DeepSeek.
- Evals: pointwise judge at temperature 0 (`eval-judge-stability`);
  faithfulness over sentence and table-cell claims with whole passages
  (`faithfulness-judge`, `judge-claim-sentences`, `judge-partial-support`,
  `judge-table-cells`); `items.jsonl` and `python -m evals.items`
  (`eval-judge-items`); forks from `chunk`, `prefilter`, `score`, `write`
  (`replay-from-chunk`, `writer-grounding`).

Numbers on the English parent `20261006-201951-1fdd38` (2 rounds, 15
pages, 56 passages): precision 0.86 to 0.88, faithfulness 0.49 old prompt
and no thinking, 0.64 with grounding rules and low thinking. Chrome chunks
7 to 0.

## The gap

Precision and faithfulness say nothing about coverage: whether the report
answers every part of the question. The gap step (`stages/gap.py`) picks
follow-up queries from a coverage table built from scores (per query:
covered, unscored, uncovered, best score, kept count) plus the best
passages so far. It never sees what the report will need. STORM and Open
Deep Research style systems find gaps from a draft or outline instead.
Before changing the gap step, a metric must exist, or the change cannot be
judged.

## Change 1: `coverage-judge`

Add a third judged metric to `python -m evals.judge`.

- **Question parts.** One LLM call per run (effort `none`, temperature 0)
  turns the run's query into a numbered list of parts: the distinct things
  the question asks for. Only the query goes through a template
  (`evals/prompts/parts.md`); answer is a JSON list of short strings;
  unparsable answer records coverage as missing. Cache the parts per
  parent run ID in `<DIR>/parts.jsonl` so every variant of the same parent
  is judged against the same parts. A long brief (the English parent is
  one) yields many parts; cap at 20.
- **Two coverage numbers**, both pointwise yes/no per part, same
  `judge_items` machinery, both recorded in `judgements.jsonl` and
  `items.jsonl` with `kind = "coverage"` and `kind = "retrievable"`:
  - `coverage`: does the report answer this part? User message holds the
    part and the report's rendered markdown (`report.json` `markdown`;
    reports are 1200 to 3000 words, fits). Missing when no `report.json`.
  - `retrievable`: do the selected passages contain enough to answer this
    part? User message holds the part and every passage text from
    `context.json` (up to ~15k tokens on the big parent; acceptable, one
    call per part). This separates "search did not find it" from "the
    writer dropped it", which is what the gap-step change needs.
- `evals.metrics` unchanged. `evals.items --failed` lists parts with
  value 0 under each kind.
- Spec: `eval-replay` ADDED requirement "Judged coverage" (do not MODIFY
  Judged precision). Scenarios: parts cached per parent, coverage with 2 of
  4 parts answered is 0.5, retrievable judged from passages only,
  missing report gives missing coverage, unparsable parts list gives both
  missing.
- Tests with the fake LLM only. `docs/design.md` Evals.

Measure before change 2: judge every existing results directory under
`evals/out/` with `--force` and note `coverage` and `retrievable` for the
parent and the full-pipeline fork. That is the baseline.

## Change 2: `draft-driven-gap`

Give the gap step the report's point of view, without a second writer call.

- **Decision taken with the user**: no full draft between rounds (a full
  write per round doubles LLM cost and time). Instead, after round k the
  gap step asks the planner LLM for an **outline check**: the data block
  gets, before the coverage table, the question parts (the same list the
  coverage judge uses, produced by the same prompt at run time by the plan
  stage, stored in `plan.json` as `parts`), and the gap prompt asks the
  model to name which parts the passages so far cannot answer and to write
  follow-ups for those first, then for `uncovered` queries. The reply gains
  `"missing": ["part", ...]`; `research.json` records `missing` per round;
  the `gap.ready` event carries it; the Research rounds panel shows it as
  a muted line under the round (reuse the note's style; the prototype has
  no such element, say so).
- The plan stage produces `parts` in the same call as the topic line and
  sub-queries (`prompts/plan.md`: one more field in the JSON answer, at
  most 12 parts; missing or malformed parts list is an empty list and a
  warning, never a failure). `Plan` model gains `parts: list[str]`.
  Single-round runs and `--sources files` keep parts (harmless) but the
  gap step does not run.
- Stop rules unchanged (`research.rounds` is a count, not a maximum).
- Specs: `research-planning` (the parts field; read its current
  requirements first), `research-rounds` (Gap step: parts in the data
  block, `missing` in the reply, round data, event), `run-events`
  (`gap.ready` data), `web-run` (Research rounds panel line), `eval-replay`
  nothing. `docs/design.md` Pipeline, Research rounds, Prompt injection
  (parts come from the plan step, which never sees scraped text; they are
  model output and go in the data block, not the template).
- Measure: replay 3 to 5 multi-round parents from `prefilter` (a fork from
  a loop stage reruns the loop from round 1, so the new gap step runs)
  with `--write`, judge, compare `coverage` and `retrievable` against the
  baseline forks. Keep precision and faithfulness in view; they must not
  drop.

## Facts to rely on

- Eval commands, run from the user's shell with their dev profile
  (`XDG_*` under `~/.local/state/wosarcher-dev`, `WOSARCHER_PROFILE=
  embeddings-jev`, secrets sourced with sudo; the agent cannot run them,
  the user pastes outputs):
  `uv run python -m evals.replay --runs <parent>... --variants <v>... --out evals/out/<dir> --write --set 'llm.model="no-think/research-smart"'`,
  `uv run python -m evals.judge --results evals/out/<dir> [--force] --set 'llm.model="no-think/research-smart"'`,
  `uv run python -m evals.items --results evals/out/<dir> --failed`.
- Parents available in the dev runs directory: `20261006-201951-1fdd38`
  (English, 2 rounds), `20261005-215825-df6f10` (English, 2 rounds),
  `20261005-181827-d75acb` and two siblings (Spanish, Peru procedures).
  More real multi-round runs help; any `wosarcher run` with `--rounds 2`
  or more is a parent. New runs land in the container; copy with
  `sudo rsync -a --chown="$(id -u):$(id -g)" /var/lib/wosarcher/share/wosarcher/runs/<id> ~/.local/state/wosarcher-dev/share/wosarcher/runs/`.
- Forks of 2-round parents rerun search and fetch (page cache) and chunk,
  so they measure the whole loop, not only ranking.
- The judge model is `no-think/research-smart` through OmniRoute; the
  judge forces effort `none` and temperature 0 and is deterministic.
- The NixOS module `~/nix-config/modules/nixos/services/ai/wosarcher/default.nix`
  generates the profiles; after a breaking config change edit it in the
  same session and tell the user to rebuild. Saved `request.json` files
  now survive removed keys (`fork-prunes-saved-settings`).
- Project rules: `AGENTS.md`, `docs/development.md`. No unit tests for
  things likely to change; stages pure; prompts in `prompts/`; scraped
  text never through a template; `scripts/check --full` is the gate.

## Non-goals

- A full draft per round.
- Changing the stop rules or the round budget arithmetic.
- A verify or repair pass on the report.
