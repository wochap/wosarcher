# Proposal

## Why

`frontend-shell` gives the browser app its frame, data layer, sign-in,
Settings, and History, but the screens that are the point of the tool are
placeholders: a person cannot start a run, watch it, read the cited
report, or rewrite it from the browser. This change builds those screens
to match every run scenario of the design prototype.

## What Changes

- **New run** screen: question, attachments (drag and drop or browse,
  `.md` and `.txt` only), collapsible Options with Run options (recipe
  `report` or `context`, sources, profile) and writing options that start
  from the saved defaults and mark per-run overrides.
- **Live run** screen: header with status, id, meta, and actions (Cancel,
  Open report, Rerun); status banner; nine-phase timeline where waiting for
  a device is shown apart from running; Sub-queries, Sources, Passages
  (0 to 1 score bars, the scorer's threshold line, rejected toggle), and a
  streaming Report panel; footer with elapsed time, tokens, cost, and
  connection; device chip with the stage's device label; phone tabs.
- Every run state of the prototype: `live`, `loading` (queued),
  `reconnecting` (banner, not a modal), `failure` (error card with Retry
  from the failed stage, Use cloud profile, Copy error), `cancelled`,
  `empty`, plus `new`.
- **Report** screen (`finished`): header and actions (Rewrite, Copy
  markdown, Download .md, Copy JSON), the report with citation chips that
  show the cited passage (text, source, score) on hover or focus, Sources
  and Selected passages.
- **Versions** (`versions`): Rewrite dialog that forks the run from the
  write stage with new writing options; versions nav linking the runs of
  one lineage; Retry from Score forks from the score stage.
- A forked run shows the data it reuses from its parent (sources marked
  cached, reused phases).
- Dev preview fixtures for every run scenario, for the manual comparison
  with the prototype.

## Non-goals

- Shell, sign-in, Settings, History, the API and event clients, and the
  run reducer: `frontend-shell`.
- No report editing, no chat over the report, no source curation.
- No PDF upload: attachments are `.md` and `.txt` only, as in the design.
- No VRAM figures in the device chip (Frontend decisions: no source has
  them).
- No backend contract changes: `report.json` and `files.jsonl` in the
  artifacts allowlist, the run summary fields (`fork_from`, `until`,
  `writing`, `duration_s`, `cost`), and `POST /api/runs/{id}/rerun` come
  from `server-api`.

## Capabilities

### New Capabilities

- `web-run`: the browser screens for one run: starting it, following it
  live in every state, reading and exporting its report with passage
  citations, and creating and browsing its versions.

### Modified Capabilities

None.

## Impact

- New code in `web/src/screens/new/`, `screens/live/`, `screens/report/`
  (replacing the placeholders), `web/src/run/` helpers (citations, score
  display, lineage), fixtures in `web/src/test/fixtures/`.
- No new dependencies (react-markdown and Phosphor come with
  `frontend-shell`).
- Depends on `frontend-shell` (ApiClient, RunEvents, `runReducer`,
  `WritingOptionsForm`, Dialog, Toast, routes) and on `server-api` (runs,
  fork, rerun, cancel, artifacts `files.jsonl`, `context.json`,
  `report.json`, `scores.jsonl`, `chunks.jsonl`).
- docs/design.md sections implemented: Frontend design and Frontend
  decisions (citations, scores, device chip, sample data replaced),
  Writing options and Citations (as shown in the UI), Attachments (upload
  rules in the UI), Commands (`--until select` as the context recipe,
  `fork --from write` as Rewrite), Server (lineage on the Versions screen,
  Rerun and Retry from Score).
- docs/design.md changes: Frontend decisions gains how a fork's reused data
  is shown and where rejected passages come from.
