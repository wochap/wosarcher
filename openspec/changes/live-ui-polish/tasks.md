## 1. Nullable `writing`

- [ ] 1.1 In `web/src/api/types.ts`, stop overriding `writing` on `RunSummary` and `RunDetail` (keep the generated `WritingOptions | null`); run the frontend typecheck and list the flagged sites. Proven by: the typecheck fails only at real null reads.
- [ ] 1.2 Fix every flagged site with `?.` and a fallback or a `kind === "catalog"` branch (`LiveScreen.tsx`, `LiveHeader.tsx`, `HistoryTable.tsx`, `HistoryScreen.tsx`, `ReportScreen.tsx`, `exportReport.ts`, and others). Proven by: the typecheck passes and existing tests stay green.
- [ ] 1.3 In `run/recent.ts`, make `rowSummary` show "Catalog · <sources> · <profile> · <N> nodes" for catalog runs (no nodes part while `nodes` is null), and make `draftFromRun` treat null `writing` as unset, filling only the question, sources, and profile for a catalog run. Proven by: new `recent.test.ts` cases for a catalog summary with `writing: null` (summary text, draft fields).
- [ ] 1.4 Add a `NewRunScreen`/`RecentRuns` test: a `GET /api/runs` fixture holding a table catalog with `writing: null` renders New run without error, and pressing its row fills without starting a run (scenario `new-recent`, "Catalog run in the list").

## 2. Failed source rows

- [ ] 2.1 In `SourcesPanel.tsx`, failed web rows show the state "failed" (danger tone), with the reason as `title` and the accessible name "failed: <reason>". Proven by: updated `SourcesPanel.test.tsx` "Failed page" (state text and title) and a new "Long failure reason" case. Compare with prototype scenario `live`: one-line rows, no horizontal scroll in the Sources panel.

## 3. Question card timeout line

- [ ] 3.1 In `QuestionCard.tsx` and `.module.css`, the line is 3px with the track always shown when `timeout > 0`, the fill is 100% while active and `left/timeout` while idle, and there is no line when `timeout` is 0. Proven by: `QuestionCard.test.tsx` cases "Line while active" (fill width 100%), "Idle countdown" (width shrinks), "Back from idle" (back to 100%), and "No timeout" (no track). Compare with prototype scenarios `live-clarify` and `live-clarify-idle`, on both a research and a catalog run.

## 4. Wrap-up

- [ ] 4.1 `scripts/check --full` passes.
