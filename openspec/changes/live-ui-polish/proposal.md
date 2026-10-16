## Why

After a catalog run with `output: table` exists, the New run screen crashes with
"can't access property "format", e.writing is null": the server sends
`writing: null` for such runs, but the client's `RunSummary`/`RunDetail` types
declare it non-null, so the Recent list reads `run.writing.format` unguarded.
Two smaller Live-screen issues ride along: a failed source's long reason
overflows the Sources panel and scrolls the whole block, and the question card's
timeout line is invisible while the user is active, so the timeout is hard to
read at a glance.

## What Changes

- `RunSummary.writing` and `RunDetail.writing` become `WritingOptions | null` in
  `web/src/api/types.ts`, matching the server; every read the compiler flags is
  made null-safe.
- Recent & pinned rows of catalog runs show "Catalog · <sources> · <profile> ·
  <N> nodes" in place of the depth, recipe, and word count, and pressing one no
  longer crashes.
- A failed source row's state reads "failed" (danger tone) with the full
  failure reason as its native tooltip and accessible name. The row no longer
  widens the panel.
- The question card's progress line becomes 3px, shows full while the user is
  active, and drains with the idle countdown; same card for research and
  catalog runs.

## Non-goals

- Filling the catalog form from a Recent row (a catalog row still fills only
  the question, sources, and profile).
- Changing the presence model or the server's timeout behaviour.
- Wrapping or truncating other Sources-panel columns.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `web-run`: Recent and pinned runs (catalog row summary, null `writing`);
  Sub-queries and sources panels (failed state text and tooltip); Question card and Presence and timeout (visible 3px line,
  full while active).

## Impact

- Code: `web/src/api/types.ts`, `web/src/run/recent.ts`,
  `web/src/screens/new/RecentRuns.tsx`, `web/src/screens/live/LiveScreen.tsx`,
  `LiveHeader.tsx`, `SourcesPanel.tsx` / `.module.css`,
  `QuestionCard.tsx` / `.module.css`, and any other site the type change flags.
- No API or server change.
- docs/design.md sections: none change; the work follows "Run questions" and "Catalog runs"
  (catalog runs carry no writing options when the output is a table).
