# Design

## Context

`frontend-shell` provides `web/` with the vendored styles, hash routes
(`#/new`, `#/live/<id>`, `#/runs/<id>`), the `ApiClient` (all `/api`
routes), `RunEvents` (WebSocket with reconnect and replay counting),
`runReducer` and `useRun(runId)` (phases with waiting, reused, skipped,
device labels; sources; kept passages with display threshold; report text;
tokens and cost; connection state), `WritingOptionsForm`, `Dialog`,
`Toast`, the overlay stack, the followed run, fake API and WebSocket for
tests, and the dev preview route. The New run, Live run, and Report
screens are placeholders. See proposal.md for scope and
`specs/web-run/spec.md` for behaviour.

Backend facts this design relies on (from the `server-api`,
`run-orchestration`, `passage-ranking`, and `report-writing` drafts):

- `POST /api/runs` takes multipart `request` (JSON: `query`, `sources`,
  `until`, `profile`, `writing` subset, `set`) plus `attachments`; 201 with
  `run_id` and status.
- `POST /api/runs/{id}/fork` takes `{from, writing?, set?, profile?}`
  (`profile` is passed to `wosarcher fork --profile`).
- `POST /api/runs/{id}/rerun` (no body) starts a new version-1 run with the
  original request and a server-side copy of its attachments.
- `GET /api/runs` items (`RunSummary`) carry `parent_run_id`, `version`,
  `fork_from`, `until`, `writing` (resolved writing options),
  `duration_s`, `cost`, `profile`, and `sources`.
- A fork logs one `stage.done` with `copied_from` per copied stage, but not
  the parent's `hit.found`, `page.fetched`, or `passages.scored`.
- `context.json` is a `Context`: `passages` (with `n`, `chunk_id`,
  `source_id`, `text`, `heading_path`, `scorer`, `display`) and `sources`
  (`kind`, `uri`, `title`, `author`, `published`).
- The final `report.md` (and the last `report.snapshot`) is the rendered
  markdown with markers in the chosen style and a References section; the
  raw body with `[n]` is in `report.json` (`body`, `markdown`, `cited`,
  `references`).
- Artifacts allowlist: `request.json`, `files.jsonl`, `plan.json`,
  `initial.jsonl`, `hits.jsonl`, `pages.jsonl`, `chunks.jsonl`,
  `candidates.jsonl`, `scores.jsonl`, `context.json`, `report.md`,
  `report.json`, `events.jsonl`, `costs.json`.
- `passages.scored` data: `query_id`, `scorer`, `scored`, `kept`,
  `threshold_display`, `passages[]` (`chunk_id`, `source_id`, `title`,
  `uri`, `heading_path`, `text`, `display`).

## Goals / Non-Goals

**Goals:**

- Each screen is a thin layout over `RunView` plus a few pure helpers that
  are unit tested (labels, display scores, lineage, markdown preparation).
- Every scenario of the prototype has a fixture, used by tests and by the
  dev preview for the manual comparison.

**Non-Goals:**

- Virtualised lists. Runs have at most a few hundred sources and passages.
- Editing writing options of a running run.

## Decisions

### Files

```
src/screens/new/      NewRunScreen.tsx, Attachments.tsx, OptionsPanel.tsx (+ .module.css)
src/screens/live/     LiveScreen.tsx, LiveHeader.tsx, StatusBanner.tsx, PhaseTimeline.tsx,
                      SubQueriesPanel.tsx, SourcesPanel.tsx, PassagesPanel.tsx,
                      ReportPanel.tsx, LiveFooter.tsx, DeviceChip.tsx, PhoneTabs.tsx,
                      FailureCard.tsx, EmptyLive.tsx (+ .module.css)
src/screens/report/   ReportScreen.tsx, ReportAside.tsx, VersionsNav.tsx, RewriteDialog.tsx
src/run/              citations.ts, scores.ts, lineage.ts, format.ts, useRunData.ts,
                      ReportMarkdown.tsx, CitationTooltip.tsx
src/test/fixtures/    live.ts, loading.ts, reconnecting.ts, failure.ts, cancelled.ts,
                      finished.ts, versions.ts
```

### Run data beyond events: `useRunData(runId)`

`useRun` gives the event view. `useRunData` adds what events do not carry:

- `GET /api/runs/{id}` once (`RunDetail`: `until`, `sources`, `profile`,
  `writing`, `parent_run_id`, `fork_from`, `version`, `duration_s`,
  `cost`).
- `files.jsonl` after `stage.done` for load (attachment pages: the
  Sources panel's file rows with title, name, and size = UTF-8 byte length
  of the page text); no events carry file sources.
- `context.json` after `stage.done` for select (citation numbers, passage
  text, display scores, sources with author and date).
- `report.json` after `stage.done` for write (raw body and references).
- `scores.jsonl` and `chunks.jsonl` only when the Rejected toggle is on and
  score is done (rejected passages, joined by `chunk_id`; display score
  via `scores.ts`).
- For a fork: the parent's view. Phases marked `reused` take their texts
  from the parent's view, sources show "cached", and passages come from the
  parent. The parent view is built by replaying the parent's events with
  `useRun(parentId)` (a finished run's socket replays and closes, so it is
  cheap); the chain is followed through `copied_from` up to the run that
  ran the stage.

Alternative: read `hits.jsonl` and `pages.jsonl` of the fork itself. Rejected:
the reducer already turns events into the panels' state; one path is
simpler than a second artifact parser.

### Display scores and thresholds (`scores.ts`)

`displayScore(scorer, value, bestForQuery)`: `jev` → value / 3, `rerank`
→ clamp(value, 0, 1), `bm25` → value / best, `passthrough` → null. Kept
passages use the server's `display` from `passages.scored`; the threshold
marker per query is `passages.scored.threshold_display`. Rejected passages share their query's
threshold. Bar width is `display × 100%`; no fixed 0.60 anywhere.

### Citations and markdown (`citations.ts`, `ReportMarkdown.tsx`)

`citationGroups(body)` finds `[n]` and `[n, m]` groups (the same pattern
as report-writing's `citations()`), and `prepare(body, streaming)` turns
each number into a link `[label](#cite-n)` and, while streaming, drops a
trailing partial `[` group and appends `[](#caret)`. `ReportMarkdown`
renders with react-markdown and overrides `a`: `#cite-n` becomes the
citation chip button (mono, accent-900 background, sizes per marker as in
the prototype), `#caret` the blinking caret, other links open in a new tab.
`label(n, marker, context)` gives `[n]`, superscript digits, or "Author,
Year" with the report-writing fallbacks (host without `www.`, file name,
"n.d."). Two sizes come from CSS: the Live panel (h3 16px, 13.5px/1.65)
and the Report article (h2 19px, 15px/1.7), the same component with a
`variant` prop. The References list comes from `report.json.references`
and is rendered after the body in the report's style.

Alternative: a remark plugin. Rejected: a link rewrite is ten lines and
needs no plugin API knowledge.

`CitationTooltip` is one fixed element owned by the screen: chip
`onMouseEnter`/`onFocus` sets `{n, rect}`, `onMouseLeave`/`onBlur` clears
it, Escape clears it through the shell's overlay stack. Position: `x =
clamp(rect.left - 20, 8, innerWidth - 372)`, below when `rect.bottom + 230 <
innerHeight`, else above with `translateY(-100%)`.

### Live screen layout

`LiveScreen` renders the header, banner, phone tabs, timeline, a grid of
column 1 (Sub-queries over Sources), Passages, and Report, and the footer,
with the prototype's grid columns (`1fr 1fr 1.35fr`, `1.2fr` below
1180px, one column and tabs below 720px). Visual states are `data-state`
attributes on the phase card, status tag, banner, source row, and passage
card, with all variants in the module CSS. The elapsed time ticks with a
1 s interval only while running.

Banner priority (one at a time): reconnecting > replaying > reconnected
(4.5 s) > cancelled > connecting/queued > rewrite. Texts are the
prototype's with "ws://localhost:8765" replaced by the page's WebSocket
origin.

Phase texts: Plan "N sub-queries"; Search "found N" then "N URLs found";
Fetch "fetched X/Y" plus " · Z failed"; Load "loaded X/Y files"; Chunk "N
chunks"; Prefilter "X/Y embedded" then "K of Y kept"; Score "scored X/Y"
then "Y scored"; Select "selecting" then "N selected"; Write "N tokens".
Counts come from the reducer (`stage.progress` `done`/`total`/`failed`,
`stage.done` `count`, sources, context). A phase skipped by the recipe
(`until`) or by `stage.done.skipped` shows done with "skipped".

### Run actions

- Start: `api.createRun(request, files)`, then `go(#/live/<id>)` and set
  the followed run. The writing part of the request holds only fields that
  differ from the loaded defaults (`overriddenFields(value, defaults)`).
- New run keeps `{query, files, options, writing}` in App state, so leaving
  and returning keeps the draft; it is cleared after a successful start.
  Defaults changed in Settings flow into non-overridden fields because the
  form stores overrides, not a copy of the defaults.
- Cancel: `api.cancelRun(id)`; the screen changes only when
  `run.cancelled` arrives.
- Rerun: `api.rerunRun(id)` (`POST /api/runs/{id}/rerun`; the server
  copies the attachments), then follow the new run on Live, as History
  does.
- Retry from <Stage>: `api.forkRun(id, {from: failedStage})`; "Use cloud
  profile": the same with `profile: "cloud"`, shown when `GET
  /api/profiles` lists `cloud` and the run's profile differs.
- Rewrite: `api.forkRun(id, {from: "write", writing: changed})`, then Live
  with the phone tab set to Report.
- Copy and download use `navigator.clipboard.writeText` and a Blob link;
  Copy JSON builds the prototype's shape from `context.json` (`cite` = `n`,
  `score` = `display`, `source` = source URI, `heading_path`, `text`).

### Versions (`lineage.ts`)

`lineage(runs, id)`: from `GET /api/runs`, walk `parent_run_id` up to the
root, then collect every run whose chain reaches that root, sorted by
`version` then `created`. Kind: "research" for the root, "rewrite" for a
fork with `fork_from == "write"`, else "fork from <fork_from>". The
description diffs each run's `writing` against its parent's `writing`
(both in the same list), formatted as the prototype's `wDiff`, plus the
run's `duration_s` as `m:ss`. No extra request is needed.

### Fixtures and preview

Each fixture is a list of typed events plus the API responses the screen
needs (`fakeApi` data), written by hand from the prototype's sample data
(same query, sub-queries, sources, failures, passages, and report text) so
the preview looks like the prototype. `#/preview/<scenario>` (dev only)
plays them: `live` streams them on a timer, the others apply them at once
(`reconnecting` closes the fake socket at seq 351 and replays after 6.5 s).

## Risks / Trade-offs

- [Parent replay for forks] → One extra socket per fork view, short-lived.
  Accepted.
- [Rejected passages need two artifacts] → `chunks.jsonl` can be a few MB;
  it is loaded only when the toggle is on and cached for the screen's
  lifetime.
- [Manual visual comparison] → Mitigated by fixtures that copy the
  prototype's sample data.
