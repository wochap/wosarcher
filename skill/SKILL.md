---
name: wosarcher
description: Research a question on the web and/or in local Markdown files and get cited passages or a cited report, using the `wosarcher` CLI (a client of a running `wosarcherd`). Use when you need sourced evidence for an answer, a literature-style summary with references, or to search a folder of notes alongside the web.
---
<!-- Install: copy or symlink this `skill/` directory into your agent's skills directory as `wosarcher/`. -->

# wosarcher

`wosarcher` plans sub-queries, searches, fetches pages, ranks passages, and
optionally writes a cited report. Read only stdout: progress goes to stderr.
Every flag is listed by `wosarcher <command> --help`.

The commands talk to a running `wosarcherd`, which holds the providers'
secrets and runs the research: over the local socket
(`$XDG_RUNTIME_DIR/wosarcher.sock`, `/run/wosarcher/api.sock`, or
`WOSARCHER_SOCKET`), or a remote daemon at `WOSARCHER_URL` with an API
token in `WOSARCHER_TOKEN`.

## 1. Cited context (default)

```sh
wosarcher run "<query>" --until select --json
```

Stops after passage selection. Cheaper and faster than a report; write your
own answer and cite passages by their number `n`, as `[n]`. Prefer this.

## 2. Full report

```sh
wosarcher run "<query>" --json
```

`report.markdown` holds the cited report with a `## References` section.

```sh
wosarcher run "<query>" --format answer --json
```

For a short cited answer: the direct answer first, then the supporting
detail, in at most `--words` words, with the same `## References` section.

## 3. Local files

```sh
wosarcher run "<query>" --attach notes.md --attach docs/ --sources both --until select --json
wosarcher run "<query>" --attach notes.md --sources files --until select --json
```

`--sources` is `files`, `web`, or `both` (default).

## 4. Profiles and overrides

```sh
wosarcher profile list
wosarcher run "<query>" --profile <profile> --until select --json
wosarcher run "<query>" --set select.max_context_tokens=8000 --until select --json
```

A profile picks providers (search, fetch, embeddings, rerank, LLM).
`--set KEY=VALUE` overrides one configuration field; repeat it for more.

```sh
wosarcher run "<query>" --allow-domain gob.pe --allow-domain sbs.gob.pe --until select --json
wosarcher run "<query>" --block-domain pinterest.com --json
```

`--allow-domain` keeps only search results from that domain and its
subdomains; `--block-domain` drops them. Repeat each flag for more
domains; the given list replaces the profile's list for this run. Entries
are bare domains (`gob.pe`), never URLs. Attachments are never filtered.

## 5. Writing options

```sh
wosarcher run "<query>" --tone analytical --words 800 --language Spanish --json
wosarcher run "<query>" --citation-marker author-year --reference-style APA --json
wosarcher run "<query>" --tone critical --tone-instructions "Focus on cost." --json
```

Tones include `objective`, `formal`, `analytical`, `critical`, and
`comparative`. Markers: `numeric`, `superscript`, `author-year`. Styles:
`APA`, `MLA`, `Chicago`, `IEEE`. `--format` is `report` (default) or
`answer`; for an answer, `--words` is a maximum.

## 6. Model and thinking

```sh
wosarcher run "<query>" --model deepseek-v4-flash --json
wosarcher run "<query>" --write-thinking high --gap-thinking low --json
```

`--model` picks the chat model for this run. `--plan-thinking`,
`--gap-thinking`, and `--write-thinking` set how much hidden reasoning each
step may do: `none` (default), `low`, `medium`, `high`, or `default` (leave
it to the server; use it when the endpoint rejects `reasoning_effort`).
Forks keep both.

## 7. Rewrite a finished run

```sh
wosarcher fork <run_id> --from write --tone critical --json
```

Copies search, fetch, and ranking from the run and only rewrites the report.

## 8. Runs and providers

```sh
wosarcher runs --json
wosarcher doctor
```

`runs` lists runs newest first. `doctor` checks that every configured
provider answers; run it when a run fails with a provider error.

## 9. Output

`--json` prints one `RunOutput` document when the run ends:

- `run_id`, `status` (`done`, `failed`, `cancelled`), `error`.
- `context.passages[]`: `n` (citation number), `source_id`, `heading_path`,
  `text`, and `display` (score, 0 to 1).
- `context.sources[]`: `source_id`, `kind` (`web` or `file`), `uri`, `title`.
- `report` (null with `--until select`): `markdown`, `cited`, `references`.

Cite a passage as `[n]` and resolve its source through `source_id`. A long
run can be followed with `wosarcher logs <run_id> --follow`.

Runs share one queue with the web UI: when every run slot is in use, the
command waits and prints `waiting for a free run slot (position <n>)` to
standard error.

Exit codes: `0` done, `1` failed (read `error`), `2` invalid arguments or
configuration (fix the command), `69` the daemon is not reachable (start
`wosarcherd serve`, or check `WOSARCHER_SOCKET`, `WOSARCHER_URL`, and
`WOSARCHER_TOKEN`), `130` cancelled (also from the web UI).

```json
{
  "run_id": "20260101-120000-a1b2c3",
  "status": "done",
  "error": null,
  "context": {
    "query": "battery recycling",
    "passages": [
      {
        "n": 1,
        "chunk_id": "517baecc904f7cbb",
        "source_id": "82930979fc30e1dc",
        "query_id": "q0",
        "text": "Battery recycling is a recycling activity that aims to reduce the number of batteries being disposed of as municipal sol…",
        "heading_path": ["Battery recycling"],
        "page_id": null,
        "block_ids": [],
        "scorer": "bm25",
        "display": 1.0
      }
    ],
    "sources": [
      {
        "source_id": "82930979fc30e1dc",
        "kind": "web",
        "uri": "https://en.wikipedia.org/wiki/Battery_recycling",
        "title": "Battery recycling - Wikipedia",
        "author": null,
        "published": null
      }
    ],
    "budget_tokens": 16000,
    "used_tokens": 1600
  },
  "report": null
}
```

## 10. Schema

```sh
wosarcher schema
```

Prints the JSON Schema of every contract. See the `RunOutput` definition
for the full output, and the `Context` and `Report` definitions for its
parts.
