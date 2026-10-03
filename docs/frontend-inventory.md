# Frontend implementation inventory

A reading aid for `design/project/Sift Research.dc.html`, so frontend work
does not have to re-read the 116 KB prototype for every detail. The
prototype in `design/` is the source of truth; where this file and the
prototype differ, the prototype wins. Product decisions that override the
prototype (name, citations, tones, scores, data sources) are in
docs/design.md, section "Frontend decisions".

All px values are from the prototype.

## 1. Screens and layout

**App shell.** One root `.sx` div (100vh, flex centred, `font-size:13.5px; line-height:1.5`, `font-variant-numeric:tabular-nums`). Inside: app frame, `flex-direction: row` (desktop) or `column` (phone).

- **Phone mode** = `device==='phone' || window.innerWidth < 720`. The "framed" phone preview (390px wide, `min(844px, calc(100vh - 32px))` tall, radius 28px, `--shadow-lg`) is prototype-only.
- **Desktop sidebar nav** (`<nav aria-label="Main">`): 184px wide, `padding:14px 10px`, gap 2px, bg `color-mix(in srgb, var(--color-surface) 45%, var(--color-bg))`, right border `1px solid var(--line)`. Brand row: `ph-funnel-simple` 18px accent, "Sift" 16px/500, version `0.9.2` mono 10.5px faint. Four items (`padding:7px 8px`, radius md, icon 16px, shortcut hint 10.5px faint on the right):
  | id | label | icon | key |
  |---|---|---|---|
  | new | New run | `ph-plus-circle` | Alt 1 |
  | live | Live run | `ph-pulse` | Alt 2 |
  | history | History | `ph-clock-counter-clockwise` | Alt 3 |
  | settings | Settings | `ph-gear-six` | Alt 4 |
  Active: bg accent 12%, text `--color-accent-300`, `aria-current="page"`. "Live run" is also active on the Report screen. A 6px status dot shows on Live (accent, `sx-pulse 1.4s`) while a run is running or connecting, and on Settings (warn, static) when any provider is not `ok`. Footer: theme toggle (`.btn.btn-secondary`, 12.5px, `ph-sun`/`ph-moon`, "Light theme"/"Dark theme") and `ws://localhost:8765` mono 10.5px faint.
- **Phone top bar**: brand icon + "Sift" 15px, then the four items as 44×44 icon buttons (icon 19px, dot at top/right 10px), then the theme toggle (44×44, muted). Bottom border `var(--line)`.
- **main**: flex 1, column, overflow hidden; each screen scrolls internally.

**Screens** (`state.screen`):

1. **New run** (max-width 800px). H1 "New research run" 26px, intro paragraph (muted). Question `textarea` (rows 6, 16px, `padding:12px 14px`, min-height 150px, placeholder about speculative decoding). Hint "Ctrl+Enter to run" with `<kbd>` (mono 11px, 1px divider border, radius 4px). `.btn-primary` "Run research" (`ph-play`), disabled when the query is blank. Attachments drop zone, file list, collapsible Options panel (Run: recipe/sources/profile; Writing: 5 fields).
2. **Live run**: header, status banner, phone tab bar, 9-phase timeline, 3-column grid (column 1 = Sub-queries over Sources; column 2 = Passages; column 3 = Report), footer status line. Desktop grid columns: `minmax(0,1fr) minmax(0,1fr) minmax(0,1.35fr)`, or `… minmax(0,1.2fr)` when width < 1180; gap 10px. Padding `14px 16px 10px` (phone `10px 10px 8px`); gap 10px (phone 8px). Desktop overflow hidden (panels scroll); phone overflow auto. Sub-queries panel: `flex:0 1 auto; max-height:42%`. Timeline: `repeat(9,minmax(0,1fr))`, gap 5px; phone `1fr 1fr`. Phone shows one tab at a time: Progress (timeline and sub-queries), Sources, Passages, Report; 4-column tablist, 44px buttons, selected = accent 10% bg, accent-300 text, `inset 0 -2px 0 var(--color-accent)`, with counts.
3. **Report** (max-width 1240px): header (Completed tag, id, meta, H1 26px / phone 21px, max-width 880px), actions, Versions nav (only when there are 2 or more versions), then a 2-column grid `minmax(0,1fr) minmax(300px,380px)`, gap 28px (single column when phone or width < 1100). Article max-width 720px, body 15px/1.7, h2 19px. Aside: Sources list and "Selected passages" cards.
4. **History** (max-width 1240px): H1 "Run history" plus count, search input (`ph-magnifying-glass` inset at 10px, `padding-left:32px`, min 220 / max 380px), Status seg (All/Completed/Failed/Cancelled), Recipe seg (Any recipe/report/context), `.table` (min-width 820px, 13px, wrapped in `overflow-x:auto`).
5. **Settings** (max-width 1240px): H1 plus "Check all providers" (`ph-heartbeat`); profile line (`ph-cpu` warn); Providers grid `repeat(auto-fill,minmax(300px,1fr))` gap 10px; Writing defaults panel (max 800px); Security panel (session, API tokens).

**Overlays** (absolute inside the frame): Rewrite dialog (z 20), Revoke alertdialog (z 20), Login lock screen (z 40), citation tooltip (fixed, z 30), toast (z 25).

**Shared metrics.** Page padding desktop `28px 32px 40px`, phone `16px 14px 24px`. Form grid `150px minmax(0,1fr)` (dialog `140px …`), `1fr` on phone. Login padding desktop `0 0 0 max(48px, 12vw)` (left-aligned form, max 340px), phone 24px.

**Theme.** The `theme` prop defaults to `dark`; the in-app toggle overrides it in state (not persisted, no `prefers-color-scheme`). The `.sx` scope adds:
- `--muted: color-mix(in srgb, var(--color-text) 64%, transparent)`, `--faint: … 42%`, `--line: … 9%`
- `--mono: ui-monospace,"SF Mono","JetBrains Mono",Menlo,Consolas,monospace`
- `--color-danger:#e58a99`, `--color-warn:#d9b56c` (not in Nocturne)
- `.sx[data-theme=light]`: bg `#f2f2f6`, surface `#fbfbfd`, text `#1d1f2c`, accent `#6b5ec4`, divider `#1d1f2c` 16%, danger `#b23c50`, warn `#8f6514`. The neutral and accent ramps are inverted (100↔900, 200↔800, 300↔700, 400↔600; 500 is unchanged). Light shadows: sm `0 0 0 1px #e1e3ee`; md `0 0 0 1px #d6d9e6, 0 6px 18px rgba(29,31,44,.08)`; lg `0 0 0 1px #c9cddd, 0 16px 40px rgba(29,31,44,.14)`. accent-2 and section tokens are not overridden.
- Other overrides: `.sx .seg{flex-wrap:wrap;max-width:100%}`, `.sx select.input{appearance:auto}`, custom scrollbar (10px, thumb `--color-divider`, 3px transparent border), `.sx a` accent with no underline; hover uses accent-300 and an underline.

## 2. Scenarios

The simulated clock runs 0 to 50 "sim-seconds". Displayed elapsed time = t × 3. The event seq shown is about t × 27.

| scenario | UI |
|---|---|
| `live` (default) | New run `r_8c21`. Status "Connecting" for 1.2s (banner `ph-circle-notch` spin "Connecting to ws://localhost:8765…", Sources skeleton), then Running through all phases. GPU waits appear on Prefilter/Score/Write. The report streams from t=34 with a blinking caret. Ends as Completed with an "Open report" button. |
| `loading` | Stays connecting (`hold`). Banner: "Connecting to ws://localhost:8765 · queued, waiting for a free worker…". Sources shows 6 shimmer skeleton rows (widths 72/58/80/64/70/52%). Sub-queries: "Waiting for the planner…". Passages: "Waiting for the run to start." All phases pending. |
| `reconnecting` | Running from t=10. At t=13 the connection drops: warn banner `ph-wifi-slash` "Connection lost. Reconnecting (attempt N)… The run continues on the server; events replay from seq 351." N increments every 2s and the display freezes at the drop time. After 6.5s: "Reconnected. Replaying N missed events…" (`ph-arrows-clockwise` spin) for 0.9s, then "Reconnected · replayed N events, nothing lost." (`ph-check-circle`) for 4.5s. Footer dot: warn pulse while reconnecting, then "Replaying", then "Connected". |
| `failure` | Running from t=18; fails at 25.4 (Score). Tag "Failed" (danger 22% bg). Score phase shows failed: "CUDA out of memory". The report panel shows an error card: "Run failed at Score", `<pre>` traceback (CUDA OOM, batch 7/12, batch_size=16), a hint, and the buttons **Retry from Score**, **Use cloud profile** and **Copy error**. The header shows "Rerun". |
| `cancelled` | Stopped at 13.2 (Fetch). Grey banner `ph-stop-circle`: "Cancelled at Fetch after 0:39. Completed stages are kept; nothing was written." Unfetched sources show "not fetched"; in-flight ones show "cancelled". Passages: "Cancelled before scoring." Report: "Cancelled before the write stage. Nothing was written." Rerun button. |
| `finished` | Report screen, v1 only (no versions nav). |
| `versions` | Report screen viewing v2 `r_8c4e` (rewrite of `r_8c21`; Concise, 250 words, superscript), with the Versions nav and the parent note "Rewritten from r_8c21 (v1): same sources and passages; changed Concise · 250 words · ¹ Superscript." |
| `empty` | Live screen with no run: `ph-pulse` 28px faint, "No run in progress", text, and a "New run" button with an "Alt 1" hint. |
| `new` | New run screen. |
| `login` | Lock screen over the New run screen. |
| `login-wrong` | Lock screen plus a danger alert "Wrong password · 3 attempts left before sign-in pauses for 30 seconds." The input border turns danger and gets `aria-invalid`. |
| `login-limited` | Warn alert `ph-timer` "Too many attempts · Sign-in is paused. Try again in 0:30." with a 2px warn countdown bar. The input is disabled. The button reads "Try again in N s" (`ph-lock-simple`). |

Other props: `speed` (0.5 to 6, simulation rate) and `emptyHistory` (bool: History shows "No runs yet" plus a New run button).

## 3. Components

| Role | Classes / icons | Notes |
|---|---|---|
| Sidebar nav item | inline; `ph-*` per item | active tint, status dot |
| Status tag | `.tag` | Connecting/Completed/Cancelled = neutral-800 bg with neutral-100 text; Running = accent-800/accent-100; Failed = danger 22%. Leading `ph-fill ph-circle` 7px, `sx-pulse` (1.2s when connecting, 1.6s when running) |
| Rewrite tag | `.tag.tag-outline`, `ph-git-branch` | "rewrite of r_xxxx" |
| GPU chip | `ph-cpu` (accent / warn / faint), `--shadow-sm` | "embeddings · 0.9 / 12 GB", "scorer · 2.3 / 12 GB", "LLM · 6.1 / 12 GB", "GPU · swapping models", "GPU idle". Low-vram profile only, desktop only |
| Status banner | `role=status`, tinted bg and border via `color-mix` | icons: wifi-slash, arrows-clockwise, check-circle, stop-circle, circle-notch, recycle |
| Phase card | `<ol aria-label=Phases>`, 3px progress bar (`transition: width .2s linear`) | 7 states (below) |
| Panel section | surface bg, `--shadow-sm`, radius md, header with 13px h2 and muted summary, `border-bottom: 1px solid var(--line)` | Sub-queries, Sources, Passages, Report |
| Source row | grid `16px minmax(0,1fr) auto` | icon; title link (13px, ellipsis) and URL (mono 11px); status (11.5px) and "N kept" (accent-300) |
| Passage card | score (mono 12px) plus a 4px bar (max 120px) with a 1px threshold marker at 60% ("threshold 0.60"), badge, `dom · heading`, text clamped to 3 lines | rejected cards at opacity .5 |
| Toggle switch | 24×14 track, 10px knob, `transition .15s`, `aria-pressed` | "Rejected" with an `R` hint |
| Citation chip | `<button>` mono, accent-900 bg, accent-200 text, radius 4px, `cursor:help`; hover accent-800 | numeric 10.5px `2px 4px`; superscript 12px `1px 2px` raised 5px; author-year 11px |
| Streaming caret | 7×14px accent block, `sx-blink 1s steps(1) infinite` | |
| Citation tooltip | `role=tooltip`, 360px (max `100vw-16px`), surface, `--shadow-lg`, `pointer-events:none` | label, score, 90px relevance bar, quoted passage, title, `dom · heading` |
| Skeleton row | shimmer gradient (`--line` → text 16% → `--line`), `background-size:480px`, `sx-shimmer 1.4s linear infinite` | |
| Segmented control | `.seg` + `.seg-opt` with hidden radio | everywhere options appear |
| Writing-options form | `.field`, `.input` textarea/number (110px, min 100, max 4000, step 50)/select (220px), `.seg` | "overridden"/"changed" `.tag-outline` 10px, Reset `.btn-ghost`, "default: X"/"was X" 11px faint |
| Drop zone | dashed 1px border (divider, accent on drag/hover), accent 8% bg on drag, `ph-file-arrow-up` 22px | `role=button`, tabIndex 0 |
| File list | surface + `--shadow-sm`, `ph-file-text`, size, `.btn-ghost.btn-icon` 30px `ph-x` | |
| Version button | 1px border (accent when current) and accent 8% bg; `ph-magnifying-glass` (research) or `ph-git-branch` (rewrite) | "v2 · rewrite r_8c4e" / diff · duration |
| Provider card | `.card.elev-sm` (`padding:12px 14px`), `.card-kicker`, `.card-title` 16px, `<dl>` grid `72px 1fr`, health strip | health icons are `ph-fill`: check-circle / warning-circle / x-circle / circle-dashed (checking, spin) |
| Data table | `.table` | history and tokens |
| History status tag | `.tag` plus 1px border | completed `ph-check` neutral; running `ph-circle-notch` spin accent; failed `ph-x-circle` danger 18%; cancelled `ph-stop-circle` transparent with divider border |
| Row actions | `.btn-ghost.btn-icon` 30px | `ph-arrow-square-out`, `ph-arrow-clockwise`, `ph-trash` (muted) |
| New-token reveal | accent border, accent 7% bg, `ph-key`, `<code>` with `user-select:all`, Copy/Copied, `ph-eye-slash` warn "Copy it now. It won't be shown again." | |
| Dialogs | `.dialog-backdrop` / `.dialog` (rewrite: `min(640px,100%)`, `max-height: calc(100% - 24px)`), `.dialog-title`, `.dialog-actions` | danger variant: `.btn-secondary` with danger color and border |
| Login screen | radial accent 8% glow `120% 80% at 0 0`, input min-height 40px, eye toggle 34px | |
| Toast | bottom 52px, centred, surface + `--shadow-md`, `ph-check`, optional Undo | 2200ms, or 6000ms when it has Undo |
| Footer status line | `ph-timer` elapsed, tokens, cost, 7px connection dot, mono `seq N` (desktop) | |

**Phase states:**

| state | icon | text | style |
|---|---|---|---|
| pending | `ph-circle` | faint | 1px `--line` border |
| waiting | `ph-cpu` | warn | 1px dashed warn border; 135° stripes (warn 14%, 5px) |
| running | `ph-circle-notch` | spin `.9s` | accent 10% bg, accent border, glow `0 0 16px -6px accent`, text accent-300 |
| done | `ph-check` | muted | divider border |
| reused | `ph-recycle` | — | dashed divider border |
| failed | `ph-x-circle` | danger | danger 10% bg, danger border |
| cancelled | `ph-stop-circle` | — | dashed muted border |

**Keyframes:** `sx-spin` (rotate 360), `sx-pulse` (opacity 1 → .3 → 1), `sx-blink` (50% opacity 0), `sx-shimmer` (bg-position -240px → 240px).

## 4. Data shown

- **Run header**: id (`r_8c21`, mono 11.5px); meta `recipe · sources · profile [· N files]`; query (17px / phone 15px, clamped to 2 lines); status (connecting/running/done/failed/cancelled); `kind` (research/rewrite), `rewriteOf`.
- **Phases** (9): plan(LLM), search, fetch, load, chunk, prefilter(embeddings), score(scorer), select, write(LLM). GPU wait reasons: "planner LLM unloading", "embeddings model unloading", "scorer unloading". Progress text: `3/5 sub-queries`, `found 14`, `fetched 12/22 · 2 failed`, `loaded 1/2 files`, `412 chunks`, `210/412 embedded` → `96 of 412 kept`, `scored 40/96` → `96 scored`, `selecting` → `14 selected`, `1.2k tokens`.
- **Sub-queries**: n, text, status (queued / searching / "8 results" / reused / cancelled); summary `3/5`.
- **Sources**: title, URL (no scheme; href `https://`+url), domain, state (found / fetching… / fetched / cached / failure reason: "403 Forbidden", "Timed out after 10 s", "Disallowed by robots.txt" / not fetched / cancelled), "N kept"; files show path, size (`4.3 KB`) and "local file". Summary `N of M fetched · 2 files`, plus "N failed · run continues". Sorted newest first. The samples carry an `ay` field (author-year, e.g. "Leviathan et al., 2023").
- **Passages**: score 0 to 1 (2 decimals), threshold 0.60, heading path joined by ` › ` (e.g. `4 Results › 4.2 Draft size vs. latency`), domain or file path, text, kept flag, citation number; badge "above threshold" / cite label / "rejected · below 0.60". Summary `40/96 scored` → `14 kept of 96 scored`.
- **Report**: markdown (`##`, `- `, `1. `, `[n]` citations); live summary `writing · 1.2k tokens`; options line `Technical · 600 words · English`.
- **Report screen**: meta `date · duration · recipe · 22 sources · 14 passages` (hard-coded); "Written with Tone · N words · Lang · Cite [· custom instructions]"; sources with "N kept" and the cite labels that use each one; count "21 · 3 failed" (hard-coded); selected passages (label, score, heading, text, domain).
- **Versions**: `{id, v, root, parent, query, opts, wopts, md, dur, date, files}`; desc = diff of writing options vs the parent, plus duration.
- **Costs and tokens**: elapsed `m:ss`; `"40.5k in · 1.2k out"` (title "Prompt / completion tokens across all stages"); cost `$0.0024`, or `$0.0000 · local`.
- **Connection**: Connecting / Connected / Reconnecting / Replaying / "Closed · run ended"; `seq N`; reconnect attempt; replayed count.
- **History row**: `{id, q, d:'Oct 2, 21:14', recipe:'report'|'context', status, dur:'3:12', cost:'$0.006', parent?, wnote:'Concise · 300 words'}`; a rewrite shows "↳ rewrite of r_7f3a · Concise · 300 words" (`ph-arrow-elbow-down-right`).
- **Providers**: `{role, name, url, modelLabel (Engines/Limits/Model), model}` for Search (SearXNG, `http://localhost:8888`, "duckduckgo, brave, arxiv"), Fetch ("httpx + trafilatura", "in-process", "timeout 10s · 6 concurrent"), Embeddings (Ollama, `bge-small-en-v1.5`), Scorer (llama.cpp server, `bge-reranker-v2-m3-Q8_0.gguf`), LLM (`qwen2.5-7b-instruct-q4_k_m.gguf`). Health `{st: ok|degraded|down, ms, at, checking}` → "Healthy · 38 ms [· 41 tok/s]", "Slow · 1,840 ms (limit 1,000 ms)", "Unreachable · ECONNREFUSED", "12 s ago".
- **Profile line**: "Profile **low-vram** · RTX 3060, 12 GB · GPU stages (embeddings, scorer, LLM) load one at a time…" (static text).
- **Writing options** `{tone, custom, words, lang, cite}`; defaults `{Technical, '', 600, English, numeric}`. Tones: Neutral, Technical, Concise, Explanatory. Languages: English, German, French, Spanish, Portuguese, Japanese, Chinese (Simplified). Cite styles: `numeric` "[1] Numeric", `super` "¹ Superscript", `authoryear` "(Author, year)".
- **Run options**: recipe `context|report`, sources `web|files|both`, profile `low-vram|workstation|cloud`.
- **API tokens**: `{name, masked:'sift_••••k9Qz', created:'Sep 12', last:'2 hours ago'|'Never'}`; new value `sift_` + 36 base62 characters. Session: "Signed in on this browser since Oct 3, 09:12."
- **Attachments**: `{name, bytes}` → `fmtB` (`B` / `KB`).
- **Copy JSON (context)** shape: `{run, parent, query, options:{recipe,sources,profile,writing:{…}}, passages:[{cite, score, source, heading_path:[…], text}]}`.

## 5. Interactions

- **Keyboard** (all disabled while locked):
  - Alt+1..4 switch screens (uses `e.code` Digit1-4).
  - Esc closes, in priority order: Revoke dialog, then Rewrite dialog, then citation tooltip.
  - `R` toggles rejected passages on Live (ignored while typing).
  - `/` focuses the History search.
  - Ctrl/Cmd+Enter submits from the question box.
  - Enter or Space on the drop zone opens the file picker.
  - Going to New run focuses the textarea after 50ms.
- **Attachments**: click, drag-over (highlight) and drop; `.md`/`.txt` only. Others are skipped with the danger alert "Skipped x.pdf — only .md and .txt are supported." Duplicate names are ignored. Remove per file.
- **Options panel**: collapsed by default (`ph-caret-right`/`-down`, `aria-expanded`). Summary line shows all values. Badge "N overridden"; per-field Reset; "Reset all to defaults"; "edit defaults" links to Settings.
- **Live**:
  - Cancel (while running or connecting) freezes at the current t.
  - Open report (when done); Rerun (when failed or cancelled) starts a new run with the same inputs.
  - Retry from Score, Use cloud profile, Copy error (on failure).
  - Rejected toggle.
  - The Report panel auto-scrolls while writing if within 140px of the bottom.
- **Citation hover/focus**: shows the tooltip under the chip (or above it if fewer than 230px remain below); x = `clamp(left-20, 8, innerWidth-372)`. Hides on leave or blur. Works on both the Live and Report screens.
- **Report**:
  - Rewrite opens a dialog prefilled with the version's options. Changed fields get a "changed" tag and "was X". Footer: "Creates v2 linked to r_8c21". Confirm with "Rewrite from write stage". Backdrop click and Esc close it.
  - Confirming starts a rewrite run: earlier phases show "reused from r_xxxx", sources show "cached", the Phone tab moves to Report, and a recycle banner shows until writing starts.
  - Copy markdown, Download .md (`<id>.md` with `# query` prepended), Copy JSON. Each shows a toast.
  - Version buttons switch versions.
- **History**:
  - Search is a case-insensitive substring match on the query; Status and Recipe filters; Clear filters.
  - Opening a row goes to Report for completed runs, Live for the active run, and the failure/cancelled scenario otherwise.
  - Rerun; Delete shows the toast "Run deleted" with Undo (6s).
  - The current run is prepended as "Today, now".
- **Settings**:
  - Check (per provider, button disabled while checking) and Check all.
  - Writing defaults autosave (prototype: localStorage `sift-writing-defaults`) and flash "Saved" (`ph-check`, 1.5s). Changing a default also updates the New run value if it was not overridden.
  - Sign out locks the app.
  - Create token (form submit, disabled when the name is empty) shows the one-time reveal with Copy and Done. Revoke asks for confirmation, then shows a toast.
- **Login**: show/hide password; submit is disabled when the field is empty; 5 attempts, then a 30s pause with a live countdown (1s tick).
- **Theme toggle** (sidebar or phone bar).

## 6. Implementation notes

**Reuse directly**
- Nocturne `styles.css`: tokens (`--color-*` and ramps, `--space-*`, `--radius-*`, `--shadow-*`, fonts) and classes `.btn*`, `.tag*`, `.field`, `.input`, `.seg/.seg-opt`, `.card*`, `.elev-*`, `.table`, `.dialog*`. Base `h1..h6` sizes are overridden inline throughout.
- The `.sx` additions (muted/faint/line/mono/danger/warn, the light theme block, scrollbar, keyframes) should become a global app stylesheet.
- Note the light theme is a prototype addition; Nocturne itself is dark-only.

**Prototype-only**
- support.js runtime: `<x-dc>`, `<helmet>`, `sc-if`/`sc-for`, `{{ }}`, `hint-placeholder-*`.
- The `data-props` scenario/speed/device switcher and the whole time simulation (`PH` s/r/e timings, `TF=3`, seq = t×27).
- Hard-coded sample data, fake health checks, client-side password `nocturne`, localStorage defaults.
- `style-hover="…"` attributes are not implemented by support.js. Turn them into real `:hover` CSS.
- Almost all styling is inline. Extract it to components or classes. Several values are computed in JS (status colours, phase state styles); move them to data-attribute or variant CSS.
- Real implementation: a reducer over the event stream keyed by `seq`, reconnect with `?since=`, and the snapshot.
