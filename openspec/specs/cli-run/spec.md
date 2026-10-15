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
`--until STAGE`, `--profile NAME`, `--use BLOCK=NAME` (repeatable),
`--depth NAME`, `--set KEY=VALUE`
(repeatable), `--tone`, `--tone-instructions`, `--words`, `--language`,
`--citation-marker`, `--reference-style`, `--format report|answer`,
`--sub-queries N`, `--results-per-query N`, `--max-pages N`,
`--passages-per-query N`, `--context-tokens N|auto`,
`--gap-context-tokens N|auto`, `--rounds N`, `--queries-per-round N`,
`--search-language CODE`, `--allow-domain DOMAIN` (repeatable),
`--block-domain DOMAIN` (repeatable), `--context-window N`,
`--max-output N`, and `--json`. The writing flags SHALL be sent as the
request's `writing`; `--sub-queries`, `--results-per-query`,
`--max-pages`, `--passages-per-query`, `--rounds`, and
`--queries-per-round` as `research`; the domain flags as `domains`;
`--search-language` as `search_language`; `--use` as `use`; `--model`, the
thinking flags, `--context-window`, `--max-output`, `--context-tokens`,
and `--gap-context-tokens` as `llm`; and `--set` as `set`, so the server
applies the precedence of http-api "Run request precedence". Values the
client can check (`--format`, the thinking levels, `--search-language`,
the domain entries, `--until`, the block of `--use`) SHALL fail with exit
status 2 before a request is sent, with an error naming the flag; a 422
from the server SHALL exit with 2 printing its detail. `--sources files`
without `--attach` SHALL fail before a request is sent.

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


#### Scenario: Entry flag
- **WHEN** the user runs `wosarcher run "q" --use score=jev-strict --use llm=agents`
- **THEN** the run's score block is the `jev-strict` entry, its llm block is the `agents` entry with that entry's default model, and `request.json` records both choices

#### Scenario: Unknown block in an entry flag
- **WHEN** the user runs `wosarcher run "q" --use scorer=bm25`
- **THEN** the command exits 2 before sending a request, naming `--use` and the blocks `search`, `fetch`, `prefilter`, `score`, `llm`

#### Scenario: Limits for an unlisted model
- **WHEN** the user runs `wosarcher run "q" --model qwen3-30b-a3b --context-window 262144 --max-output 16384`
- **THEN** the resolved `llm.context_window` is 262144 and `llm.max_output_tokens` is 16384

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
flags, `--model`, the thinking flags, `--context-window`, `--max-output`,
`--context-tokens`, `--gap-context-tokens`, `--use`, `--until`,
`--profile`, and `--json`, and create the fork through
`POST /api/runs/{id}/fork`. The server's `wosarcherd fork` SHALL resolve
the fork as the run store defines (run-store "Fork"): with `--profile
NAME` from that profile, the fork's `--use`, and the parent's overrides
plus the new overrides, recording `NAME` as its profile; without
`--profile`, from the parent's saved settings with each `--use` block
replaced by the current entry. When the parent's saved settings hold a key
the current configuration does not know, it SHALL drop that key before
validation, print one warning line naming every dropped key as a dotted
path, and continue with a `request.json` without those keys; a saved value
the current configuration rejects SHALL still fail. A queued or running
parent SHALL exit with 2 printing the server's 409 detail.

#### Scenario: Change the tone
- **WHEN** the user runs `wosarcher fork <id> --from write --tone critical`
- **THEN** a new run with the next version of the parent's lineage is created and only the write stage runs

#### Scenario: Retry with another scorer
- **WHEN** the user runs `wosarcher fork <id> --from score --use score=bm25`
- **THEN** the fork's score block is the current `bm25` entry, its other blocks keep the parent's saved settings, and its record names `bm25` as the score entry

#### Scenario: Retry with another profile
- **WHEN** the user runs `wosarcher fork <id> --from score --profile cloud`
- **THEN** the fork's blocks come from the entries the `cloud` profile uses and its record names profile `cloud`

#### Scenario: Stale saved key
- **WHEN** the parent's `request.json` settings hold `prefilter.top_k = 50` and the field no longer exists
- **THEN** the fork starts, the server log has a warning naming `prefilter.top_k`, and its `request.json` settings have no `prefilter.top_k`

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
with ID, creation time, kind (`research` or `catalog`), status (`queued`,
`running`, `done`, `failed`, `cancelled`, or `interrupted`), origin,
version, parent run ID, and query. `--limit N` SHALL limit the list
(default 20), `--kind research|catalog` SHALL keep only that kind, and
`--json` SHALL print the list as a JSON array of `RunSummary`.

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

#### Scenario: Catalog run listed
- **WHEN** a finished catalog run of 118 records is listed
- **THEN** its line shows the kind `catalog` and `wosarcher runs --kind research` leaves it out

### Requirement: Logs command
`wosarcher logs <run-id> [--follow]` SHALL print the run's logged events
from the daemon, one line each: `<HH:MM:SS> <stage or -> <type>
<summary>`, where the time is the event time in local time and the summary
is a short description of `data` (newlines replaced by spaces, at most 160
characters). For `node.found` the summary SHALL be `<id> depth <d> ←
<parent id or seed>`; for `node.extracted`, `<id> <n> values · <n>
children · <n> flags`; for `node.failed`, `<id> <reason>`; for
`wave.done`, `wave <k> expanded <n> found <n> records <n> failed <n>`; for
`catalog.done`, `<waves> waves · <records> records · <flagged> flagged ·
<reason>`. Without `--follow` it SHALL read `events.jsonl` through the
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

#### Scenario: Catalog events printed
- **WHEN** the user runs `wosarcher logs <id>` for a finished catalog run
- **THEN** its `wave.done` lines read like "wave 1 expanded 6 found 14 records 6 failed 0" and the `catalog.done` line names the stop reason

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
`--set llm.model="NAME"` and choosing the model whose entry values apply
(run-config "Precedence"), `--context-window N` and `--max-output N`
(positive integers), acting as `--set llm.context_window=N` and
`--set llm.max_output_tokens=N`, and the thinking flags, each taking
`none`, `low`, `medium`, `high`, or `default` and acting as `--set
llm.reasoning.<step>=<value>`: `wosarcher run` takes `--plan-thinking`,
`--gap-thinking`, and `--write-thinking`; `wosarcher fork` takes all five
(`--draft-thinking` and `--extract-thinking` too) and SHALL fail with exit
status 2 before a request is sent when a flag's step does not belong to
the parent run's kind, naming the flag and the kind. Any other value SHALL
exit 2 before a run is created, naming the flag and the allowed values.
These flags SHALL take precedence over `--set` for the same field and
SHALL be recorded in `request.json` like other overrides, so forks and
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

#### Scenario: Invalid window
- **WHEN** the user runs `wosarcher run "q" --context-window 0`
- **THEN** the command exits with status 2 before creating a run, naming `--context-window`

#### Scenario: Fork keeps thinking
- **WHEN** a run was started with `--write-thinking high` and the user runs `wosarcher fork <id> --from write --tone critical`
- **THEN** the fork's resolved `llm.reasoning.write` is `high`

#### Scenario: Re-extract with a level
- **WHEN** the user runs `wosarcher fork <id> --from extract --extract-thinking medium` on a catalog run
- **THEN** the fork's resolved `llm.reasoning.extract` is `medium`

#### Scenario: Wrong kind for a fork flag
- **WHEN** the user runs `wosarcher fork <id> --from write --extract-thinking low` on a research run
- **THEN** the command exits with status 2 naming `--extract-thinking` and `research`

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

### Requirement: Client environment defaults
`wosarcher run` SHALL take `WOSARCHER_DEPTH` from the client's own
environment as the value of `--depth`, and `WOSARCHER_PROFILE` as the value
of `--profile`, when the flag is not given, and send it in the run request
exactly as the flag would be sent. A flag on the command line SHALL win
over its variable. A variable that is unset or empty SHALL count as absent,
leaving the request's `depth` or `profile` empty as today. A name the
daemon does not know SHALL fail like the same flag: the server's 422 detail
printed and exit status 2. `wosarcher run --help` SHALL name each variable
next to its flag. `wosarcher fork` SHALL NOT read either variable: a fork
without `--profile` SHALL keep rebuilding from the parent's saved settings.

#### Scenario: Depth from the environment
- **WHEN** the client's environment has `WOSARCHER_DEPTH=quick` and the user runs `wosarcher run "q" --until select --json`
- **THEN** the run's `request.json` records depth `quick` and the resolved `fetch.max_pages` is the `quick` preset's

#### Scenario: Flag wins over the environment
- **WHEN** the client's environment has `WOSARCHER_DEPTH=quick` and `WOSARCHER_PROFILE=lan` and the user runs `wosarcher run "q" --depth deep --profile cloud`
- **THEN** the run's `request.json` records depth `deep` and profile `cloud`

#### Scenario: Profile from the environment
- **WHEN** the client's environment has `WOSARCHER_PROFILE=lan`, the daemon's stored default profile is `desktop`, and the user runs `wosarcher run "q"`
- **THEN** the run's `request.json` records profile `lan`

#### Scenario: Empty variable
- **WHEN** the client's environment has `WOSARCHER_DEPTH=` (empty) and the user runs `wosarcher run "q"`
- **THEN** the request carries no depth and the run's `request.json` records no depth

#### Scenario: Unknown depth from the environment
- **WHEN** the client's environment has `WOSARCHER_DEPTH=quik` and the user runs `wosarcher run "q"`
- **THEN** the command exits with 2 printing the server's detail naming `depth`, and no run is created

#### Scenario: Fork ignores the environment
- **WHEN** the client's environment has `WOSARCHER_PROFILE=cloud` and the user runs `wosarcher fork <id> --from write --tone critical`
- **THEN** the fork is rebuilt from the parent's saved settings and its record names the parent's profile, not `cloud`

### Requirement: Catalog command
`wosarcher catalog "<brief>"` SHALL start a catalog run through the
daemon's API and accept: `--structure FILE` (a JSON structure file),
`--seed "NAME|TYPE[|URL]"` (repeatable), `--relation TEXT`, `--leaf TYPE`
(repeatable), `--expand links|search|both`, `--output table|report|both`,
`--max-depth N`, `--max-nodes N`, `--pages-per-node N`,
`--search-language CODE`, `--allow-domain` and `--block-domain`
(repeatable), `--attach PATH` (repeatable), `--sources web|both` (default
`both`), `--profile`, `--use BLOCK=NAME` (repeatable), `--model`,
`--draft-thinking` and `--extract-thinking` (each `none`, `low`, `medium`,
`high`, or `default`, acting as `--set llm.reasoning.<step>=<value>`),
`--context-window`, `--max-output`, the writing flags of `wosarcher run`
(`--tone`, `--tone-instructions`, `--words`, `--language`,
`--citation-marker`, `--reference-style`, `--format report|answer`; sent
as `writing`, and rejected with exit status 2 naming `--output` when the
output is `table`), `--set KEY=VALUE` (repeatable), `--until STAGE`, and
`--json`. It SHALL NOT accept `--plan-thinking`, `--gap-thinking`, or
`--write-thinking`. The structure flags SHALL be applied over the file's
values (seeds and leaf types from flags replace the file's lists); with no
`--structure` and no structure flag, the request carries no structure and
the `draft` stage derives one. With structure flags but no file, the
command SHALL fail before a request is sent when the flags do not make a
complete structure (no seed, or no relation), naming what is missing.
Values the client can check (`--expand`, `--output`, the limits' ranges,
the thinking values, `--until` against the catalog stages,
`--search-language`, the domain entries, the block of `--use`) SHALL fail
with exit status 2 before a request is sent; a 422 SHALL exit with 2
printing its detail. The command SHALL follow the run's events as
`wosarcher run` does, with the catalog phases and a wave counter, and the
report streamed when one is written. When the run ends it SHALL print:
for `output` `table`, the `records` array of `catalog.json` as JSON; for
`report` or `both`, the report as Markdown. `--json` SHALL print
`catalog.json` with, when a report was written, a `report` key holding
`report.json`. A run that ends without `catalog.json` (stopped early with
`--until`) SHALL print nothing and exit 0.

#### Scenario: Structure file
- **WHEN** the user runs `wosarcher catalog "Every public organization…" --structure peru.json --allow-domain gob.pe`
- **THEN** the request has `kind` `catalog`, the file's structure, and `domains.allow` `["gob.pe"]`, and the records array is printed when the run ends

#### Scenario: Flags over the file
- **WHEN** the file sets `max_nodes` 200 and the user passes `--max-nodes 50`
- **THEN** the request's structure has `max_nodes` 50

#### Scenario: Derived structure
- **WHEN** the user runs `wosarcher catalog "brief"` with no structure flag
- **THEN** the request carries no structure and the run's `draft` stage makes the draft call

#### Scenario: Incomplete flags
- **WHEN** the user passes `--seed "PCM|ministry"` and no `--relation` or `--structure`
- **THEN** the command fails with exit status 2 naming `--relation`

#### Scenario: Extract thinking flag
- **WHEN** the user runs `wosarcher catalog "brief" --extract-thinking low`
- **THEN** the request has `llm.reasoning.extract` `low` and `request.json` records the override

#### Scenario: Research thinking flag rejected
- **WHEN** the user runs `wosarcher catalog "brief" --write-thinking high`
- **THEN** the command fails with exit status 2 as an unknown option

#### Scenario: Report output
- **WHEN** the user runs `wosarcher catalog "brief" --structure s.json --output report --words 800`
- **THEN** the request's structure has `output` `report`, `writing.words` is 800, the report streams during the write stage, and the Markdown report is printed at the end

#### Scenario: Writing flag without a report
- **WHEN** the user runs `wosarcher catalog "brief" --structure s.json --tone critical` and the structure's output is `table`
- **THEN** the command fails with exit status 2 naming `--tone` and `--output`

#### Scenario: JSON with a report
- **WHEN** the user runs `wosarcher catalog "brief" --structure s.json --output both --json`
- **THEN** the printed JSON holds `records` and a `report` key with the report body and references

### Requirement: Catalog draft command
`wosarcher catalog draft "<brief>"` SHALL post the brief (and `--attach`
files, `--profile`, `--use`, and the llm flags) to `POST /api/catalog/draft`
and print the structure as JSON, so it can be edited and passed back with
`--structure`. A 502 SHALL exit with 1 printing the reason.

#### Scenario: Draft to a file
- **WHEN** the user runs `wosarcher catalog draft "brief" > peru.json`
- **THEN** `peru.json` holds a structure that `wosarcher catalog "brief" --structure peru.json` accepts
