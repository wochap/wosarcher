## Context

`models.py` (`RunSummary.writing`, `RunDetail.writing`) is `WritingOptions | None`:
`None` for a catalog run whose `output` is `table`. The generated client types
(`web/src/api/generated.ts`) already say `writing?: WritingOptions | null`, but
`web/src/api/types.ts` overrides both with a non-null `writing: WritingOptions`.
The override hides every unguarded read. The one users hit is `rowSummary` in
`run/recent.ts`, which runs for every Recent & pinned row on New run, so a single
table catalog in `GET /api/runs` breaks the screen after a reload.

The Sources panel row is a grid `16px minmax(0,1fr) auto`. Its state cell is
`white-space: nowrap`, and a failed row puts the whole `reason` in it. A long
reason grows the `auto` column, which widens the panel content and adds a
horizontal scrollbar to the whole block.

`QuestionCard` already has a progress line (`.track` / `.fill`), but while the
user is active `left` is `null`, so `pct` is 0 and the track is transparent:
the line only appears after 10 idle seconds. Both research and catalog Live
screens render the same `QuestionCard`.

## Goals / Non-Goals

**Goals:**
- The type matches the server, and the compiler finds every null read.
- Recent rows of catalog runs render and fill without error.
- Failed source rows stay one line wide; the reason is still reachable.
- The timeout line is always visible on a card with a timeout.

**Non-Goals:**
- Filling the catalog form (structure, limits) from a Recent row.
- Any server, presence, or timeout-enforcement change.

## Decisions

1. **Drop the non-null override in `types.ts`, not add local guards.**
   `RunSummary` / `RunDetail` keep the generated `writing: WritingOptions | null`
   (optional, from `G.*`). `scripts/check-frontend`'s typecheck then lists every
   unsafe site. Fix each with `?.` and a fallback, or branch on `kind === "catalog"`.
   Alternative: guard only `recent.ts`. Rejected because the next new caller
   would crash the same way.

2. **Catalog Recent summary.** `rowSummary` branches on `run.kind === "catalog"`:
   `["Catalog", sources, profileLabel, nodes != null && "<N> nodes"]`, with
   falsy parts dropped. `draftFromRun` for a catalog run fills the question,
   sources, and profile only; it treats null `writing` as `{}`. `duplicateKey`
   is already null-safe.

3. **Failed state: short text, reason in `title`.** `webRow` returns
   `state: "failed"` and a new `stateTitle: s.reason`. The state `<div>` gets
   `title={stateTitle}` and `aria-label="failed: <reason>"` when a reason
   exists. No CSS change is needed: "failed" is short, and `nowrap` stays.
   Alternative: wrap the reason under the URL. Rejected because it makes rows
   taller and noisier in long failure lists.

4. **Progress line: `pct = left === null ? 100 : left / timeout * 100`.** The
   track is always `var(--line)` when `timeout > 0`, height 3px, and the
   `data-idle` attribute stays for styling and tests. The `transition` stays
   at 0.2s linear, so the reset to full is a short animation. The whole track
   is hidden when `timeout` is 0.

## Risks / Trade-offs

- [Making `writing` nullable may surface many sites at once] → Most sites only
  render for research runs. Use `?.` with the research default, and do not
  reshape the logic.
- [A native tooltip is not visible on touch] → The accessible name carries the
  reason. The phone layout is unchanged otherwise, and this is acceptable for
  a diagnostic detail.
- [A full bar while active could read as "nothing is happening"] → The chip
  next to it says "waiting for you", so the meaning stays explicit.
