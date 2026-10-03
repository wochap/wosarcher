# Tasks

Visual checks are manual: open `design/project/Sift Research.dc.html` with
the named scenario next to `#/preview/<scenario>` in `pnpm --dir web dev`,
in the dark and light themes, at 1440px, 1100px, and 390px wide, and
compare layout, sizes, colors, icons, and text.

## 1. Helpers

- [ ] 1.1 Implement `src/run/format.ts` (`fmtElapsed` m:ss, `fmtK`, `fmtBytes` B/KB, `fmtCost` with "· local" for zero, `wSummary`, `wDiff` as in the prototype); verify `format.test.ts` with the prototype's examples
- [ ] 1.2 Implement `src/run/scores.ts` (`displayScore` for jev, rerank, bm25, passthrough; rejected passages from `scores.jsonl` + `chunks.jsonl` rows); verify `scores.test.ts`: jev 2.4 → 0.8, rerank 1.3 → 1, bm25 relative to the query's best, passthrough → null
- [ ] 1.3 Implement `src/run/citations.ts` (`citationGroups`, `prepare` with partial-marker trim and caret, `label` for numeric, superscript, author-year with host, file name, and "n.d." fallbacks); verify `citations.test.ts`: `[1, 2]` gives two chips, trailing `[1` is dropped while streaming, `www.example.org` without date gives "example.org, n.d."
- [ ] 1.4 Implement `src/run/lineage.ts` (`lineage(runs, id)` over `RunSummary` items, kind from `fork_from`, description from the `writing` diff against the parent and `duration_s`); verify `lineage.test.ts` for a root with two rewrites (`fork_from` `write`) and a fork of a fork from `score` ("fork from score")
- [ ] 1.5 Implement `src/run/useRunData.ts` (run detail, `files.jsonl` after load done for file sources, `context.json` after select done, `report.json` after write done, rejected artifacts on demand, parent view for forks via `copied_from`); verify `useRunData.test.tsx` with `fakeApi` and fixture events: artifacts fetched only after their stage is done, file rows have the page text's byte size, fork shows the parent's sources as cached

## 2. Fixtures

- [ ] 2.1 Write fixtures `src/test/fixtures/{live,loading,reconnecting,failure,cancelled,finished,versions}.ts` from the prototype's sample data (query, five sub-queries, 22 sources with the three failures, 2 files, passages with scores, report text, CUDA OOM error) and register them in `src/dev/preview.tsx`; verify each fixture type-checks against the generated types and `#/preview/<scenario>` renders without errors in a smoke test

## 3. New run (scenario `new`)

- [ ] 3.1 Implement `src/screens/new/NewRunScreen.tsx` (+ CSS): H1, intro with "wosarcher", Question textarea focused on open, Ctrl/Cmd+Enter, "Run research" disabled when blank, draft kept in App state; verify `NewRunScreen.test.tsx`; compare with scenario `new` (manual) (spec: New run form)
- [ ] 3.2 Implement `src/screens/new/Attachments.tsx`: drop zone (click, Enter, Space, drag highlight), `.md`/`.txt` filter with the skip alert, duplicate names ignored, file list with size and remove; verify `Attachments.test.tsx` with a mixed drop and remove; compare with `new` with files added (manual) (spec: Attachments)
- [ ] 3.3 Implement `src/screens/new/OptionsPanel.tsx`: collapsed header with summary and "N overridden", Run group (Recipe, Sources from settings default, Profile from `GET /api/profiles`), Writing group with `WritingOptionsForm` (`mark="overridden"`, `baseLabel="default: "`), Reset all, "edit defaults" link; verify `OptionsPanel.test.tsx`: one override shows the marks, default change in Settings follows when not overridden; compare with `new` with Options open (manual) (spec: Run options, Writing overrides)
- [ ] 3.4 Wire start: `createRun` with `until: "select"` for context, only overridden writing fields, attachments; on success go to `#/live/<id>` and set the followed run, on error keep inputs and show the message; verify tests for the request body and the error path (spec: Start a run)

## 4. Live run (scenarios `live`, `loading`, `reconnecting`, `failure`, `cancelled`, `empty`)

- [ ] 4.1 Implement `LiveHeader.tsx` and `DeviceChip.tsx` (status tag variants, rewrite tag, id, meta, clamped query, Cancel/Open report/Rerun, chip with labels only, desktop only); verify `LiveHeader.test.tsx` for each status and the chip texts; compare with `live` (manual) (spec: Live run header, Device chip)
- [ ] 4.2 Implement `PhaseTimeline.tsx` (nine cards, seven `data-state` variants, texts from design.md, 3px bar, phone two columns); verify `PhaseTimeline.test.tsx`: waiting text and style differ from running, reused names the parent, skipped; compare with `live` mid-run (manual) (spec: Phase timeline)
- [ ] 4.3 Implement `SubQueriesPanel.tsx` and `SourcesPanel.tsx` (row grid, states found/fetched/cached/failed/not fetched/file size, "N kept", summary, fail note, newest first, skeleton rows); verify tests for a failed page and a cancelled run; compare with `live` and `loading` (manual) (spec: Sub-queries and sources panels)
- [ ] 4.4 Implement `PassagesPanel.tsx` (score, bar, per-query threshold marker, badge, heading path, three-line clamp, Rejected toggle and R key, passthrough "–", empty texts, summaries); verify `PassagesPanel.test.tsx`: threshold 0.5 marker at 50%, R shows rejected at half opacity; compare with `live` after scoring (manual) (spec: Passages panel)
- [ ] 4.5 Implement `src/run/ReportMarkdown.tsx`, `CitationTooltip.tsx`, and `ReportPanel.tsx` (streaming body with chips and caret, auto-scroll within 140px, header summary and options, waiting texts); verify `ReportPanel.test.tsx` for chips per marker, caret only while writing, auto-scroll, and tooltip content and placement above when near the bottom; compare with `live` while writing (manual) (spec: Streaming report panel, Citations)
- [ ] 4.6 Implement `LiveFooter.tsx`, `StatusBanner.tsx`, and `PhoneTabs.tsx` (elapsed, tokens, cost, connection dot and text, seq on desktop; banner priority and texts with the page's socket origin; four tabs with counts); verify tests for "$0.0000 · local", the reconnect sequence attempt 1, attempt 2, replaying 54, replayed 54 then hidden after 4.5 s, and tab switching; compare with `reconnecting` and `live` at 390px (manual) (spec: Live footer, Reconnecting state, Phone live layout)
- [ ] 4.7 Implement `LiveScreen.tsx` composing the parts with the prototype grid and breakpoints, the `loading` state (queued banner, skeletons, waiting texts), and `EmptyLive.tsx`; verify `LiveScreen.test.tsx` for queued, empty, and completed with "Open report"; compare with `loading` and `empty` (manual) (spec: Queued state, No run state)
- [ ] 4.8 Implement `FailureCard.tsx` and the failed and interrupted states (Retry from <Stage> fork, Use cloud profile when available, Copy error, Rerun with `api.rerunRun(id)`) and the cancelled state (banner, not fetched sources, empty texts, Rerun), plus Cancel calling `cancelRun`; verify tests: retry sends `from: "score"`, Use cloud profile sends `from` and `profile: "cloud"`, Rerun sends `POST /api/runs/{id}/rerun`, cloud button hidden without a `cloud` profile, cancelled banner names Fetch; compare with `failure` and `cancelled` (manual) (spec: Failure state, Cancelled state)

## 5. Report and versions (scenarios `finished`, `versions`)

- [ ] 5.1 Implement `ReportScreen.tsx` and `ReportAside.tsx` (header, meta from run data, actions, "Written with" line, `ReportMarkdown` article variant with References, Sources with kept counts and cite labels, Selected passages; context recipe shows passages instead of the report); verify `ReportScreen.test.tsx` with the `finished` fixture and a context-recipe fixture; compare with `finished`, desktop, 1100px, and phone (manual) (spec: Report screen, Citations)
- [ ] 5.2 Implement export actions (Copy markdown from `report.md`, Download `<id>.md` with `# query`, Copy JSON from `context.json`) with toasts; verify tests for the download name and content and the JSON shape (spec: Export)
- [ ] 5.3 Implement `RewriteDialog.tsx` (`WritingOptionsForm` with `mark="changed"`, `baseLabel="was "`, compact columns; reuse note; "Creates v<N> linked to <id>"; Cancel, close, Escape, backdrop) and confirm with `forkRun({from: "write", writing})`, then Live with the Report tab on phone and the rewrite banner; verify `RewriteDialog.test.tsx`: only changed fields sent, Escape sends nothing; compare with the prototype's Rewrite dialog from `finished` (manual) (spec: Rewrite)
- [ ] 5.4 Implement `VersionsNav.tsx` and the parent note (lineage buttons with kind, id, description, current marking; hidden for a single run); verify `VersionsNav.test.tsx` with the `versions` fixture; compare with `versions` (manual) (spec: Versions)

## 6. Documentation and gate

- [ ] 6.1 Update docs/design.md "Frontend decisions": a fork shows its parent's sources (cached) and passages for reused phases; rejected passages come from `scores.jsonl` and `chunks.jsonl` with the server's display mapping; citation chips are built from the `[n]` body and labelled by the client; verify the section matches the code
- [ ] 6.2 Verify `scripts/check --full` passes and `openspec validate frontend-run --strict` passes
