# cli-run Specification

## Purpose

Gives people and agents commands to start a run, fork a finished run, and
list runs, with readable progress on a terminal and stable JSON for scripts.

## Requirements

### Requirement: Run command
`wosarcher run "<query>"` SHALL start a run through the daemon's API and
accept these options:
`--attach PATH` (repeatable; files, directories, globs, expanded and
uploaded by the client), `--sources files|web|both` (default `both`),
`--until STAGE`, `--profile NAME`, `--depth NAME`, `--set KEY=VALUE`
(repeatable), `--tone`, `--tone-instructions`, `--words`, `--language`,
`--citation-marker`, `--reference-style`, `--format report|answer`,
`--sub-queries N`, `--results-per-query N`, `--max-pages N`,
`--passages-per-query N`, `--context-tokens N|auto`,
`--gap-context-tokens N|auto`, `--rounds N`, `--queries-per-round N`,
`--search-language CODE`, `--allow-domain DOMAIN` (repeatable),
`--block-domain DOMAIN` (repeatable), and `--json`. The writing flags SHALL
be sent as the request's `writing`, the research flags as `research`, the
domain flags as `domains`, `--search-language` as `search_language`,
`--model` and the thinking flags as `llm`, and `--set` as `set`, so the
server applies the precedence of http-api "Run request precedence". Values
the client can check (`--format`, the thinking levels, `--search-language`,
the domain entries, `--until`) SHALL fail with exit status 2 before a
request is sent, with an error naming the flag; a 422 from the server
SHALL exit with 2 printing its detail. `--sources files` without
`--attach` SHALL fail before a request is sent.

#### Scenario: Writing flag
- **WHEN** the user runs `wosarcher run "q" --tone critical --words 500`
- **THEN** the run's resolved writing options have tone `critical` and words 500, and `request.json` lists both overrides

#### Scenario: Files without attachments
- **WHEN** the user runs `wosarcher run "q" --sources files` with no `--attach`
- **THEN** the command fails before sending a request, with an error that `--sources files` needs `--attach`

#### Scenario: Unknown stage
- **WHEN** the user runs `wosarcher run "q" --until rank`
- **THEN** the command fails with an error listing the valid stage names

#### Scenario: Depth with a research flag
- **WHEN** the user runs `wosarcher run "q" --depth deep --max-pages 80`
- **THEN** the resolved `fetch.max_pages` is 80, `plan.max_sub_queries` is 6, and `request.json` records depth `deep` and the `fetch.max_pages` override

#### Scenario: Attachments uploaded
- **WHEN** the user runs `wosarcher run "q" --attach notes/ --sources files --until load --json`
- **THEN** every Markdown file under `notes/` is uploaded and appears in the run's `attachments/` on the daemon's host

#### Scenario: Domain flags
- **WHEN** the profile sets `search.allow_domains = ["gob.pe"]` and the user runs `wosarcher run "q" --allow-domain sunat.gob.pe --allow-domain sbs.gob.pe --block-domain facebook.com`
- **THEN** the resolved `search.allow_domains` is `["sunat.gob.pe", "sbs.gob.pe"]`, `search.block_domains` is `["facebook.com"]`, and `request.json` records both overrides

#### Scenario: Invalid domain flag
- **WHEN** the user runs `wosarcher run "q" --allow-domain "https://gob.pe/x"`
- **THEN** the command fails with exit status 2 before sending a request, with an error that names the entry

#### Scenario: Unknown format
- **WHEN** the user runs `wosarcher run "q" --format summary`
- **THEN** the command exits with status 2 before sending a request, with an error naming `--format` and the values `report` and `answer`

#### Scenario: Invalid search language
- **WHEN** the user runs `wosarcher run "q" --search-language "spanish please"`
- **THEN** the command exits with status 2 before sending a request, with an error naming `--search-language`

#### Scenario: Server rejects an override
- **WHEN** the user runs `wosarcher run "q" --set score.topk=3`
- **THEN** the run fails before its first stage, the command prints the configuration error, and exits with 2

#### Scenario: Rounds flag
- **WHEN** the user runs `wosarcher run "q" --depth deep --rounds 2`
- **THEN** the resolved `research.rounds` is 2

#### Scenario: Auto context flag
- **WHEN** the user runs `wosarcher run "q" --profile p --context-tokens auto` and profile `p` sets `select.max_context_tokens = 12000`
- **THEN** the resolved `select.max_context_tokens` is `auto`

#### Scenario: Gap context flag
- **WHEN** the user runs `wosarcher run "q" --depth deep --gap-context-tokens auto`
- **THEN** the resolved `research.gap_context_tokens` is `auto` and `request.json` records that override

#### Scenario: Answer format flag
- **WHEN** the user runs `wosarcher run "q" --format answer`
- **THEN** the run's resolved writing options have format `answer` and `request.json` records the `write.format` override

#### Scenario: Follow-ups per round flag
- **WHEN** the user runs `wosarcher run "q" --depth deep --queries-per-round 6`
- **THEN** the resolved `research.queries_per_round` is 6 and `request.json` records that override

#### Scenario: Search language flag
- **WHEN** the user runs `wosarcher run "q" --search-language es-PE`
- **THEN** the resolved `search.language` is `es-PE` and SearXNG receives `language=es-PE` with every query

#### Scenario: Invalid language through --set
- **WHEN** the user runs `wosarcher run "q" --set search.language='"spanish"'`
- **THEN** the run fails before its first stage with an error naming `search.language`, and the command exits with 2

### Requirement: Human output
On a terminal, `wosarcher run` SHALL show live progress per stage (state,
counters, device, provider) built from the run's event stream and, when
the run ends, print the report as Markdown, or a summary of the context
when the run stopped at `select`, both fetched from the run's artifacts.
When standard output is not a terminal and `--json` is not given, it SHALL
print the report Markdown without progress. Progress, diagnostics, and
errors SHALL go to standard error: the live progress view when standard
error is a terminal and `--json` is not given, otherwise one diagnostic
line per run and stage event (the same lines run-lifecycle "Diagnostics on
standard error" defines for the run process).

#### Scenario: Piped output
- **WHEN** the user runs `wosarcher run "q" > report.md`
- **THEN** `report.md` contains only the report Markdown

#### Scenario: Standard error piped
- **WHEN** the user runs `wosarcher run "q" 2> run.log`
- **THEN** `run.log` has one line per stage start and end, and no progress view escape codes

### Requirement: JSON output
With `--json`, `wosarcher run` and `wosarcher fork` SHALL print exactly one
JSON document to standard output when the run ends: run ID, status, error,
the selected context (passages with numbers, chunk IDs, sources, heading
paths, text, and scores) when the select stage finished, and the report
(Markdown and references) when the write stage finished. `wosarcherd run`
and `wosarcherd fork` SHALL print the same document. Its schema SHALL be
included in `wosarcher schema`.

#### Scenario: Cited context for agents
- **WHEN** an agent runs `wosarcher run "q" --until select --json`
- **THEN** standard output is one JSON document with `status` `done`, a `context` with numbered passages and their sources, and `report` null

#### Scenario: Failed run
- **WHEN** a run with `--json` fails in the fetch stage
- **THEN** standard output is one JSON document with `status` `failed` and the error, and the exit status is 1

### Requirement: Exit status
`wosarcher run` and `wosarcher fork` SHALL exit with 0 when the run ends
with `run.done`, 1 when it ends with `run.failed`, 130 when it is
cancelled, 2 for invalid arguments or a request the server rejects, and 69
when the daemon cannot be reached.

#### Scenario: Invalid override
- **WHEN** the user runs `wosarcher run "q" --set score.topk=3`
- **THEN** the command exits with 2

#### Scenario: Daemon unreachable
- **WHEN** nothing listens on the client's socket and the user runs `wosarcher run "q"`
- **THEN** the command exits with 69 and no run is created

#### Scenario: Removed concurrency setting
- **WHEN** the user runs `wosarcher run "q" --set server.max_concurrent_runs=2`
- **THEN** the command exits with 2 and the error names the unknown key

### Requirement: Fork command
`wosarcher fork <run_id> --from <stage>` SHALL accept `--set`, the writing
flags, `--model`, the thinking flags, `--until`, `--profile`, and
`--json`, and create the fork through `POST /api/runs/{id}/fork`. The
server's `wosarcherd fork` SHALL resolve the fork as the run store defines:
with `--profile NAME` from that profile and the parent's overrides plus the
new overrides, recording `NAME` as its profile; when the parent's saved
settings hold a key the current configuration does not know, dropping that
key before validation, printing one warning line naming every dropped key
as a dotted path, and continuing with a `request.json` without those keys;
a saved value the current configuration rejects SHALL still fail. A
queued or running parent SHALL exit with 2 printing the server's 409
detail.

#### Scenario: Change the tone
- **WHEN** the user runs `wosarcher fork <id> --from write --tone critical`
- **THEN** a new run with the next version of the parent's lineage is created and only the write stage runs

#### Scenario: Retry with another profile
- **WHEN** the user runs `wosarcher fork <id> --from score --profile cloud`
- **THEN** the fork's score block comes from the `cloud` profile and its record names profile `cloud`

#### Scenario: Stale saved key
- **WHEN** the parent's `request.json` settings hold `llm.reasoning_tokens = 4096` and the field no longer exists
- **THEN** the fork starts, the server log has a warning naming `llm.reasoning_tokens`, and its `request.json` settings have no `reasoning_tokens`

#### Scenario: Parent still running
- **WHEN** the user forks a run that is running
- **THEN** the command exits with 2 and prints the server's detail

#### Scenario: Rewrite as an answer
- **WHEN** the user runs `wosarcher fork <id> --from write --format answer`
- **THEN** only the write stage runs, with format `answer`, and the fork's `request.json` records the `write.format` override

#### Scenario: Stale saved value
- **WHEN** the parent's settings hold `llm.provider = "llm"` and only `openai` is accepted
- **THEN** the fork fails before its first stage naming `llm.provider`, and the command exits with 1 printing the error

### Requirement: Runs command
`wosarcher runs` SHALL list the runs `GET /api/runs` returns, newest first,
with ID, creation time, status (`queued`, `running`, `done`, `failed`,
`cancelled`, or `interrupted`), origin, version, parent run ID, and query.
`--limit N` SHALL limit the list (default 20) and `--json` SHALL print the
list as a JSON array of `RunSummary`.

#### Scenario: Status from the log
- **WHEN** a run's last run event is `run.failed`
- **THEN** `wosarcher runs` shows its status as `failed`

#### Scenario: Interrupted run
- **WHEN** a run's log has `run.started` and no terminal event, and no process holds its run lock
- **THEN** `wosarcher runs` shows its status as `interrupted`

#### Scenario: Run started in the browser
- **WHEN** a run started from the web UI is running
- **THEN** `wosarcher runs` shows its status as `running` and its origin as `web`

#### Scenario: Run started by the server
- **WHEN** a run started by the server from an API token is running
- **THEN** `wosarcher runs` shows its status as `running` and its origin as `api · <token name>`

### Requirement: Logs command
`wosarcher logs <run-id> [--follow]` SHALL print the run's logged events
from the daemon, one line each: `<HH:MM:SS> <stage or -> <type>
<summary>`, where the time is the event time in local time and the summary
is a short description of `data` (newlines replaced by spaces, at most 160
characters). Without `--follow` it SHALL read `events.jsonl` through the
artifacts route and skip lines that do not parse. With `--follow`, it SHALL
subscribe to the run's event socket from `since=0`, print each logged event
as it arrives (live-only events are not printed), and exit with 0 after a
terminal event. An unknown run SHALL exit with 2 and an error naming the
run.

#### Scenario: Finished run
- **WHEN** the user runs `wosarcher logs <id>` for a run that failed in fetch
- **THEN** each logged event is printed on one line in `seq` order, the last one is `run.failed` with stage `fetch` and the first line of the error, and the exit status is 0

#### Scenario: Follow a running run
- **WHEN** the user runs `wosarcher logs <id> --follow` while the run is in the score stage
- **THEN** the events so far are printed, then each new event as it is logged, and the command exits with 0 after `run.done`

#### Scenario: Unknown run
- **WHEN** the user runs `wosarcher logs does-not-exist`
- **THEN** the command exits with 2 and the error names `does-not-exist`

#### Scenario: Long data shortened
- **WHEN** a `page.failed` event has a 200-character reason
- **THEN** its printed line's summary is at most 160 characters

### Requirement: Round progress
The CLI progress view SHALL show a `gap` row for multi-round runs only. A
loop stage's row SHALL show "round <k>/<N>" while it runs, and the number
of rounds it ran when done. The gap row SHALL show the follow-up count
after each gap step. When research ends, the view SHALL print one line:
"research: <ran> of <planned> rounds · <stop reason>".

#### Scenario: Multi-round progress
- **WHEN** a three-round run is in round 2's fetch
- **THEN** the fetch row shows "round 2/3"

#### Scenario: Research line
- **WHEN** a deep run stops after round 2 with `no new sources`
- **THEN** the view prints "research: 2 of 3 rounds · no new sources"

### Requirement: Model and thinking flags
`wosarcher run` and `wosarcher fork` SHALL accept `--model NAME`, acting as
`--set llm.model="NAME"`, and `--plan-thinking`, `--gap-thinking`, and
`--write-thinking`, each taking `none`, `low`, `medium`, `high`, or
`default` and acting as `--set llm.reasoning.<step>=<value>`. Any other
value SHALL exit 2 before a run is created, naming the flag and the five
values. These flags SHALL take precedence over `--set` for the same field
and SHALL be recorded in `request.json` like other overrides, so forks and
reruns keep them. Without a flag the configured value is left unchanged.

#### Scenario: Model flag
- **WHEN** the user runs `wosarcher run "q" --model deepseek-v4-flash`
- **THEN** the resolved `llm.model` is `deepseek-v4-flash` and `request.json` records the override

#### Scenario: Thinking flags
- **WHEN** the user runs `wosarcher run "q" --write-thinking high --gap-thinking low`
- **THEN** the resolved `llm.reasoning.write` is `high`, `llm.reasoning.gap` is `low`, and `llm.reasoning.plan` keeps the configured value

#### Scenario: Invalid thinking value
- **WHEN** the user runs `wosarcher run "q" --plan-thinking max`
- **THEN** the command exits with status 2 before creating a run, naming `--plan-thinking` and the values `none`, `low`, `medium`, `high`, `default`

#### Scenario: Fork keeps thinking
- **WHEN** a run was started with `--write-thinking high` and the user runs `wosarcher fork <id> --from write --tone critical`
- **THEN** the fork's resolved `llm.reasoning.write` is `high`

### Requirement: Queued run shown
While a run created by `wosarcher run` or `wosarcher fork` is queued, the
command SHALL write `waiting for a free run slot (position <n>)` to
standard error when it starts waiting and whenever `run.queued` reports a
new position; on a terminal the progress view SHALL show the same text
above the stage rows. SIGINT or SIGTERM while the run is queued or running
SHALL send `POST /api/runs/{id}/cancel`, wait for the run's terminal
event, and exit with 130.

#### Scenario: Waiting shown
- **WHEN** `max_concurrent_runs = 1`, a run is running, and an agent runs `wosarcher run "q" --json`
- **THEN** standard error has `waiting for a free run slot (position 1)`, and the run starts when the other run ends

#### Scenario: Ctrl-C while queued
- **WHEN** the user presses Ctrl-C while `wosarcher run` waits in the queue
- **THEN** the run is dequeued, its status is `cancelled`, and the command exits with 130

#### Scenario: Ctrl-C while running
- **WHEN** the user presses Ctrl-C while the run is in `fetch`
- **THEN** the run's log ends with `run.cancelled` and the command exits with 130
