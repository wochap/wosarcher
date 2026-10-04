# Frontend implementation inventory

A reading aid for `design/project/wosarcher.dc.html`, so frontend work does
not have to re-read the prototype for every detail. The prototype in
`design/` is the source of truth; where this file and the prototype differ,
the prototype wins. Product decisions that override the prototype (citations,
tones, scores, data sources) are in docs/design.md, section "Frontend
decisions".

All px values are from the prototype.

## 1. Screens and layout

**App shell.** One root `.sx` div (100vh, flex centred, `font-size:13.5px; line-height:1.5`, `font-variant-numeric:tabular-nums`). Inside: app frame, `flex-direction: row` (desktop) or `column` (phone).

- **Phone mode** = `device==='phone' || window.innerWidth < 720`. The "framed" phone preview (390px wide, `min(844px, calc(100vh - 32px))` tall, radius 28px, `--shadow-lg`) is prototype-only.
- **Desktop sidebar nav** (`<nav aria-label="Main">`): 184px wide, `padding:14px 10px`, gap 2px, bg `color-mix(in srgb, var(--color-surface) 45%, var(--color-bg))`, right border `1px solid var(--line)`. Brand row (`padding:2px 8px 16px`): `ph-funnel-simple` 18px accent, "wosarcher" 16px/500, no version. Four items (`padding:7px 8px`, radius md, icon 16px, shortcut hint 10.5px faint on the right):
  | id | label | icon | key |
  |---|---|---|---|
  | new | New run | `ph-plus-circle` | Alt 1 |
  | live | Live run | `ph-pulse` | Alt 2 |
  | history | History | `ph-clock-counter-clockwise` | Alt 3 |
  | settings | Settings | `ph-gear-six` | Alt 4 |
  Active: bg accent 12%, text `--color-accent-300`, `aria-current="page"`. "Live run" is also active on the Report screen. A 6px status dot shows on Live (accent, `sx-pulse 1.4s`) while a run is running or connecting, and on Settings (warn, static) when any provider is not `ok`. Footer: theme toggle (`.btn.btn-secondary`, 12.5px, `ph-sun`/`ph-moon`, "Light theme"/"Dark theme") and `ws://localhost:8765` mono 10.5px faint.
- **Phone top bar**: brand icon + "wosarcher" 15px, then the four items as 44×44 icon buttons (icon 19px, dot at top/right 10px), then the theme toggle (44×44, muted). Bottom border `var(--line)`.
- **main**: flex 1, column, overflow hidden; each screen scrolls internally.

**Screens** (`state.screen`):

1. **New run** (max-width 800px). H1 "New research run" 26px, intro "wosarcher searches the web and your files, scores passages for relevance, and writes a cited report." (muted). Question `textarea` (rows 6, 16px, `padding:12px 14px`, min-height 150px, placeholder about speculative decoding on 12 GB GPUs). Hint "Ctrl+Enter to run" with `<kbd>` (mono 11px, 1px divider border, radius 4px). `.btn-primary` "Run research" (`ph-play`), disabled when the query is blank. "Attachments" label (12px muted, help `attach`), drop zone, file list, collapsible Options panel.
   - **Options › Run** (uppercase 11px heading): rows in the form grid, label 12.5px plus one help button per row. Rows in order: Recipe (seg report/context, help `recipe`), Sources (seg web/files/both, help `sources`), Profile (select `width:min(260px,100%)`, options are the profile ids with "  (user profile)" appended for user profiles; below it the profile description, 12px muted, `margin-top:4px`; help `profile`).
   - **Options › Writing**: heading plus "Preselected from your defaults ·", an "edit defaults" ghost link to Settings, and "Reset all to defaults" (`ph-arrow-counter-clockwise`) when anything is overridden. Six writing fields (see the Writing-options form in §3).
2. **Live run**: header, status banner, phone tab bar, 9-phase timeline, 3-column grid (column 1 = Sub-queries over Sources; column 2 = Passages; column 3 = Report), footer status line. Desktop grid columns: `minmax(0,1fr) minmax(0,1fr) minmax(0,1.35fr)`, or `… minmax(0,1.2fr)` when width < 1180; gap 10px. Padding `14px 16px 10px` (phone `10px 10px 8px`); gap 10px (phone 8px). Desktop overflow hidden (panels scroll); phone overflow auto. Sub-queries panel: `flex:0 1 auto; max-height:42%`. Timeline: `<ol>` grid `repeat(9,minmax(98px,1fr))`, gap 5px, `overflow-x:auto`, `padding-bottom:2px`; phone `1fr 1fr`. Phone shows one tab at a time: Progress (timeline and sub-queries), Sources, Passages, Report; 4-column tablist, 44px buttons, selected = accent 10% bg, accent-300 text, `inset 0 -2px 0 var(--color-accent)`, with counts. Header actions: Device chip, Cancel, Open report, Rerun (with help `rerun`).
3. **Report** (max-width 1240px): header (Completed tag, id, meta, H1 26px / phone 21px, max-width 880px), actions (Rewrite with help `rewrite`, Copy markdown, Download .md, Copy JSON (context)), Versions nav (only when there are 2 or more versions; heading help `versions`), then a 2-column grid `minmax(0,1fr) minmax(300px,380px)`, gap 28px (single column when phone or width < 1100). Article max-width 720px, body 15px/1.7, h2 19px; ends with a "References" h2 showing the reference style (12px muted) and help `w-ref`, then the formatted reference list (13.5px/1.55, URL mono 12px muted; IEEE adds `[n]` marks mono 12px, min-width 30px). Aside: Sources list and "Selected passages" cards.
4. **History** (max-width 1240px): H1 "Run history" plus count, search input (`ph-magnifying-glass` inset at 10px, `padding-left:32px`, min 220 / max 380px), Status seg (All/Completed/Failed/Cancelled), Recipe seg (Any recipe/report/context), `.table` (min-width 820px, 13px, wrapped in `overflow-x:auto`). Column headers Recipe (help `h-recipe`) and Cost (help `h-cost`); the rewrite sub-line has help `h-version`.
5. **Settings** (max-width 1240px): H1 plus "Check all providers" (`ph-heartbeat`), then a wrapping line (gap `10px 22px`, 12.5px) with two parts:
   - **Active profile**: `ph-cpu` muted 15px, "Active profile" muted, the profile name mono 12px, help `profile`, then "· <description>" muted.
   - **GPU policy**: "GPU policy" plus help `gpupolicy`, a seg Shared/Exclusive (`.seg-opt` `padding:4px 10px; font-size:12.5px`), and an explanation 12px muted: "Each model unloads before the next one loads on <gpuDev>." (exclusive) or "All models stay loaded on <gpuDev>." (shared).
   - **Providers** (uppercase 13px heading): grid `repeat(auto-fill,minmax(300px,1fr))` gap 10px of provider cards (§3): `<dl>` with an 84px label column and rows Base URL, Model/Engines/Limits, Device (help `pdevice`), Unload (help `unload`); health strip with help `health`.
   - **Writing defaults** heading plus help `wdefaults`, "Preselected on every new run · saved automatically", "Saved" flash; panel max 800px with the six writing fields.
   - **Security**: Session row, "API tokens" (help `apitokens`), create form, token table.
6. **Help spec** (`helpspec`, max-width 1300px): a design page for the help component, reached only through the `help` scenario (§2).

**Overlays**: Rewrite dialog (absolute, z 20), Revoke alertdialog (absolute, z 20), Login lock screen (absolute, z 40), help tooltip (fixed, z 35), citation tooltip (fixed, z 30), toast (absolute, z 25).

**Shared metrics.** Page padding desktop `28px 32px 40px`, phone `16px 14px 24px`. Form grid `150px minmax(0,1fr)` (dialog `140px …`), `1fr` on phone. Login padding desktop `0 0 0 max(48px, 12vw)` (left-aligned form, max 340px), phone 24px. Login brand "wosarcher" 19px with a 22px funnel icon; text "Enter the password for this wosarcher instance."

**Theme.** The `theme` prop defaults to `dark`; the in-app toggle overrides it in state (not persisted, no `prefers-color-scheme`). The `.sx` scope adds:
- `--muted: color-mix(in srgb, var(--color-text) 64%, transparent)`, `--faint: … 42%`, `--line: … 9%`
- `--mono: ui-monospace,"SF Mono","JetBrains Mono",Menlo,Consolas,monospace`
- `--color-danger:#e58a99`, `--color-warn:#d9b56c` (not in Nocturne)
- `--wa-ring:#9397ab` (help tooltip arrow border); light `#c9cddd`
- `.sx[data-theme=light]`: bg `#f2f2f6`, surface `#fbfbfd`, text `#1d1f2c`, accent `#6b5ec4`, divider `#1d1f2c` 16%, danger `#b23c50`, warn `#8f6514`. The neutral and accent ramps are inverted (100↔900, 200↔800, 300↔700, 400↔600; 500 is unchanged). Light shadows: sm `0 0 0 1px #e1e3ee`; md `0 0 0 1px #d6d9e6, 0 6px 18px rgba(29,31,44,.08)`; lg `0 0 0 1px #c9cddd, 0 16px 40px rgba(29,31,44,.14)`. accent-2 and section tokens are not overridden.
- Other overrides: `.sx .seg{flex-wrap:wrap;max-width:100%}`, `.sx select.input{appearance:auto}`, custom scrollbar (10px, thumb `--color-divider`, 3px transparent border), `.sx a` accent with no underline; hover uses accent-300 and an underline.

## 2. Scenarios

The simulated clock runs 0 to 50 "sim-seconds". Displayed elapsed time = t × 3. The event seq shown is about t × 27.

| scenario | UI |
|---|---|
| `live` (default) | New run `r_8c21`. Status "Connecting" for 1.2s (banner `ph-circle-notch` spin "Connecting to ws://localhost:8765…", Sources skeleton), then Running through all phases. GPU waits appear on Prefilter/Score/Write. The report streams from t=34 with a blinking caret. Ends as Completed with an "Open report" button. |
| `loading` | Stays connecting (`hold`). Banner: "Connecting to ws://localhost:8765 · queued, waiting for a free worker…". Sources shows 6 shimmer skeleton rows (widths 72/58/80/64/70/52%). Sub-queries: "Waiting for the planner…". Passages: "Waiting for the run to start." All phases pending. |
| `reconnecting` | Running from t=10. At t=13 the connection drops: warn banner `ph-wifi-slash` "Connection lost. Reconnecting (attempt N)… The run continues on the server; events replay from seq 351." N increments every 2s and the display freezes at the drop time. After 6.5s: "Reconnected. Replaying N missed events…" (`ph-arrows-clockwise` spin) for 0.9s, then "Reconnected · replayed N events, nothing lost." (`ph-check-circle`) for 4.5s. Footer dot: warn pulse while reconnecting, then "Replaying", then "Connected". |
| `failure` | Running from t=18; fails at 25.4 (Score). Tag "Failed" (danger 22% bg). Score phase shows failed: "CUDA out of memory". The report panel shows an error card: "Run failed at Score", `<pre>` traceback (CUDA OOM, batch 7/12, batch_size=16), a hint, and the buttons **Retry from Score** (help `retry`), **Use cloud profile** and **Copy error**. The header shows "Rerun". |
| `cancelled` | Stopped at 13.2 (Fetch). Grey banner `ph-stop-circle`: "Cancelled at Fetch after 0:39. Completed stages are kept; nothing was written." Unfetched sources show "not fetched"; in-flight ones show "cancelled". Passages: "Cancelled before scoring." Report: "Cancelled before the write stage. Nothing was written." Rerun button. |
| `finished` | Report screen, v1 only (no versions nav). |
| `versions` | Report screen viewing v2 `r_8c4e` (rewrite of `r_8c21`; Informative, 250 words, superscript), with the Versions nav and the parent note "Rewritten from r_8c21 (v1): same sources and passages; changed Informative · 250 words · ¹ Superscript." |
| `empty` | Live screen with no run: `ph-pulse` 28px faint, "No run in progress", text, and a "New run" button with an "Alt 1" hint. |
| `new` | New run screen. |
| `help` | Help spec screen. H1 "Inline help" 26px and a muted intro (max 660px): a 16px "?" after any non-obvious label or column header; hover or focus opens it on desktop, a tap on a phone; tapping outside or Esc closes; one open at a time. Four static figures (caption uppercase 11px muted, stage on `--color-bg` with `--shadow-sm`, caption text 12px muted): **A · Closed** (240px; Recipe label, faint "?", seg; "Muted Phosphor question, 4–5px after the label…"); **B · Hover / focus open** (330px; "?" with a 2px accent outline offset 2px, tooltip below with the arrow at the top; notes `role="tooltip"` and `aria-describedby`); **C · Phone, tap open** (300px, radius 24px; Profile "?" pinned: accent-300 on accent 22%; low-vram select and its description; tooltip below; footer "Tap outside or press Esc to close"; notes the invisible 28px tap area); **D · Near an edge, flipped** (330px; Cost header "?" at bottom right, tooltip opens above and slides left, arrow at the bottom pointing at the button). Below: a "Try the live component:" row with live help buttons for Recipe (`recipe`), Prefilter (`ph-prefilter`), "Score, waiting for GPU" (`wait-score`), Scorer (`scorer`) and Cost (`h-cost`, pushed right). |
| `login` | Lock screen over the New run screen. |
| `login-wrong` | Lock screen plus a danger alert "Wrong password · 3 attempts left before sign-in pauses for 30 seconds." The input border turns danger and gets `aria-invalid`. |
| `login-limited` | Warn alert `ph-timer` "Too many attempts · Sign-in is paused. Try again in 0:30." with a 2px warn countdown bar. The input is disabled. The button reads "Try again in N s" (`ph-lock-simple`). |

Other props: `speed` (0.5 to 6, simulation rate), `device` (`auto`/`phone`) and `emptyHistory` (bool: History shows "No runs yet" plus a New run button).

## 3. Components

| Role | Classes / icons | Notes |
|---|---|---|
| Sidebar nav item | inline; `ph-*` per item | active tint, status dot |
| Help button | `<button type="button" data-help="<key>">`, `ph-question` 15px (line-height 1) | 16px round, no padding or border, transparent, color `--faint`, `cursor:help`, `vertical-align:middle`, `flex:none`; `::before` with `inset:-6px` enlarges the hit area to 28px. Hover: `--color-text` on text 8% tint. Pinned (help spec figure C): accent-300 on accent 22%. Focus shows the Nocturne ring. `aria-label="Help: <label>"`, `aria-describedby="wa-help"`. Sits 4–5px after its label |
| Help tooltip | `#wa-help`, `role=tooltip` | `position:fixed; z-index:35`, 272px wide (max `calc(100vw - 16px)`), `padding:9px 12px 10px`, radius md, surface bg, `--shadow-lg`, column gap 4px, 13px/1.45, weight 400, no text-transform or letter-spacing, left-aligned. Title 600; body `text-wrap:pretty`; optional "Example:" line 12px muted with the example mono 11.5px in text color. Arrow: 10×10 surface square rotated 45°, at top -6px (below) or bottom -6px (above), with 1px `--wa-ring` borders on top+left (below) or bottom+right (above). Placement from the button rect: `x = clamp(cx − 136, 8, vw − 280)`; opens below when `bottom + 180 < vh` or `top < 180`, else above (`translateY(-100%)`); 9px gap; arrow x = `clamp(cx − x − 5, 10, 252)`. Receives pointer events (hovering it keeps it open) |
| Status tag | `.tag` | Connecting/Completed/Cancelled = neutral-800 bg with neutral-100 text; Running = accent-800/accent-100; Failed = danger 22%. Leading `ph-fill ph-circle` 7px, `sx-pulse` (1.2s when connecting, 1.6s when running) |
| Rewrite tag | `.tag.tag-outline`, `ph-git-branch` | "rewrite of r_xxxx" |
| Device chip | `ph-cpu` (accent while a GPU phase runs, warn while one waits, faint otherwise), `--shadow-sm`, radius md | `padding:4px 7px 4px 9px`, gap 6px, 12px muted; device label mono 11.5px: "<gpuDev>" (GPU phase running), "<gpuDev> · waiting" (GPU phase waiting), else "<cpuDev>". Help `device`. Shown while running or connecting, desktop only |
| Status banner | `role=status`, tinted bg and border via `color-mix` | icons: wifi-slash, arrows-clockwise, check-circle, stop-circle, circle-notch, recycle |
| Phase card | `<li>` in `<ol aria-label=Phases>`, `padding:7px 9px 0`, 3px progress bar (`transition: width .2s linear`) | No title attribute. Label row 12.5px/500: icon 14px, label `flex:1; min-width:max-content; white-space:nowrap`, help button keyed `ph-<phase>`, or `wait-<phase>` (label "Help: <Phase>, waiting for GPU") when waiting. Text line 11.5px ellipsis. 7 states (below) |
| Panel section | surface bg, `--shadow-sm`, radius md, header with 13px h2 and muted summary, `border-bottom: 1px solid var(--line)` | Sub-queries, Sources, Passages, Report |
| Passages header | flex, `flex-wrap:wrap`, `gap:4px 8px`, `padding:6px 8px 6px 12px` | h2 "Passages"; scorer tag `.tag.tag-neutral` mono 10.5px `padding:1px 6px` plus help `scorer`; summary 12px muted (`flex:1`, nowrap) "<n>/96 scored · ≥ 0.60" or "14 kept of 96 · ≥ 0.60" plus help `score`; Rejected toggle plus help `rejected` |
| Source row | grid `16px minmax(0,1fr) auto` | icon; title link (13px, ellipsis) and URL (mono 11px); status (11.5px) and "N kept" (accent-300) |
| Passage card | score (mono 12px) plus a 4px bar (max 120px) with a 1px threshold marker at the profile threshold (title "threshold 0.60"), badge, `dom · heading`, text clamped to 3 lines | rejected cards at opacity .5 |
| Toggle switch | 24×14 track, 10px knob, `transition .15s`, `aria-pressed` | "Rejected" with an `R` hint |
| Citation chip | `<button>` mono, accent-900 bg, accent-200 text, radius 4px, `cursor:help`; hover accent-800 | numeric 10.5px `2px 4px`; superscript 12px `1px 2px` raised 5px; author-year 11px |
| Streaming caret | 7×14px accent block, `sx-blink 1s steps(1) infinite` | |
| Citation tooltip | `role=tooltip`, 360px (max `100vw-16px`), surface, `--shadow-lg`, `pointer-events:none` | label, score, 90px relevance bar, quoted passage, title, `dom · heading` |
| Skeleton row | shimmer gradient (`--line` → text 16% → `--line`), `background-size:480px`, `sx-shimmer 1.4s linear infinite` | |
| Segmented control | `.seg` + `.seg-opt` with hidden radio | everywhere options appear |
| Writing-options form | `.field`, `.input`, `.seg` | Fields in order, labels 12.5px each with a help button (`w-<key>`): Tone (select, options "<Tone> — <description>"), Custom instructions (textarea min-height 64px, dialog 60px; placeholder "e.g. Focus on costs; avoid jargon."), Length (words) (number 110px, min 100, max 4000, step 50, suffix "words, approximately", dialog "words"), Language (select), Citation marker (seg), Reference style (seg APA/MLA/Chicago/IEEE). Selects `width:min(380px,100%)`. When a value differs from its base: mark `.tag-outline` 10px "overridden" (help `overridden`) or "changed" (help `rwchanged`), Reset `.btn-ghost` 11.5px, then "default: X" / "was X" 11px faint. Custom text in these and in diffs is shown quoted and cut to 28 chars plus "…", or "none" |
| Drop zone | dashed 1px border (divider, accent on drag/hover), accent 8% bg on drag, `ph-file-arrow-up` 22px | `role=button`, tabIndex 0 |
| File list | surface + `--shadow-sm`, `ph-file-text`, size, `.btn-ghost.btn-icon` 30px `ph-x` | |
| Version button | 1px border (accent when current) and accent 8% bg; `ph-magnifying-glass` (research) or `ph-git-branch` (rewrite) | "v2 · rewrite r_8c4e" / diff · duration |
| Provider card | `.card.elev-sm` (`gap:8px; padding:12px 14px`), `.card-kicker`, Check ghost button, `.card-title` 16px, `<dl>` grid `84px minmax(0,1fr)` gap `3px 10px` 12px, values mono 11.5px | rows Base URL, Model/Engines/Limits, Device (help `pdevice`), Unload (help `unload`). Health strip (`padding:6px 9px`, 12.5px, help `health`, "N s ago" 11px faint); icons are `ph-fill`: check-circle / warning-circle / x-circle / circle-dashed (checking, spin) |
| Data table | `.table` | history and tokens |
| History status tag | `.tag` plus 1px border | completed `ph-check` neutral; running `ph-circle-notch` spin accent; failed `ph-x-circle` danger 18%; cancelled `ph-stop-circle` transparent with divider border |
| Row actions | `.btn-ghost.btn-icon` 30px | `ph-arrow-square-out`, `ph-arrow-clockwise`, `ph-trash` (muted) |
| New-token reveal | accent border, accent 7% bg, `ph-key`, `<code>` with `user-select:all`, Copy/Copied, `ph-eye-slash` warn "Copy it now. It won't be shown again." | |
| Dialogs | `.dialog-backdrop` / `.dialog` (rewrite: `min(640px,100%)`, `max-height: calc(100% - 24px)`), `.dialog-title`, `.dialog-actions` | danger variant: `.btn-secondary` with danger color and border |
| Login screen | radial accent 8% glow `120% 80% at 0 0`, input min-height 40px, eye toggle 34px | |
| Toast | bottom 52px, centred, surface + `--shadow-md`, `ph-check`, optional Undo | 2200ms, or 6000ms when it has Undo |
| Footer status line | `ph-timer` elapsed, tokens, cost plus help `tokens`, 7px connection dot, mono `seq N` (desktop) | |

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
- **Phases** (9): plan(LLM), search, fetch, load, chunk, prefilter(embeddings), score(scorer), select, write(LLM). GPU wait reasons: "planner LLM unloading", "embeddings model unloading", "scorer unloading"; waiting text "waiting for GPU · <reason>". Progress text: `3/5 sub-queries`, `found 14` → `22 URLs found`, `fetched 12/22 · 2 failed`, `loaded 1/2 files`, `412 chunks`, `210/412 embedded` → `96 of 412 kept`, `scored 40/96` → `96 scored`, `selecting` → `14 selected`, `1.2k tokens`.
- **Sub-queries**: n, text, status (queued / searching / "8 results" / reused / cancelled); summary `3/5`.
- **Sources**: title, URL (no scheme; href `https://`+url), domain, state (found / fetching… / fetched / cached / failure reason: "403 Forbidden", "Timed out after 10 s", "Disallowed by robots.txt" / not fetched / cancelled), "N kept"; files show path, size (`4.3 KB`) and "local file". Summary `N of M fetched · 2 files`, plus "N failed · run continues". Sorted newest first. The samples carry an `ay` field (author-year, e.g. "Leviathan et al., 2023").
- **Passages**: score 0 to 1 (2 decimals), threshold from the profile, heading path joined by ` › ` (e.g. `4 Results › 4.2 Draft size vs. latency`), domain or file path, text, kept flag, citation number; badge "above threshold" / cite label / "rejected · below 0.60". Scorer tag from the profile.
- **Report**: markdown (`##`, `- `, `1. `, `[n]` citations); live summary `writing · 1.2k tokens`; options line `Objective · 1200 words · English`.
- **Report screen**: meta `date · duration · recipe · 22 sources · 14 passages` (hard-coded); "Written with Tone · N words · Lang · Cite · Ref [· custom instructions]"; References in the chosen style (APA `Au (yr). Title. dom.`, MLA `Au. “Title.” dom, yr.`, Chicago `Au. yr. “Title.” dom.`, IEEE `[n] Au, “Title,” dom, yr.`; files use "Local notes", missing year "n.d."); sources with "N kept" and the cite labels that use each one; count "21 · 3 failed" (hard-coded); selected passages (label, score, heading, text, domain).
- **Versions**: `{id, v, root, parent, query, opts, wopts, md, dur, date, files}`; desc = diff of writing options vs the parent (custom shows as "custom instructions"), plus duration; "full run · dur" for v1.
- **Costs and tokens**: elapsed `m:ss`; `"40.5k in · 1.2k out"` (title "Prompt / completion tokens across all stages"); cost `$0.0024`, or `$0.0000 · local`.
- **Connection**: Connecting / Connected / Reconnecting / Replaying / "Closed · run ended"; `seq N`; reconnect attempt; replayed count.
- **History row**: `{id, q, d:'Oct 2, 21:14', recipe:'report'|'context', status, dur:'3:12', cost:'$0.006', parent?, wnote:'Informative · 300 words'}`; a rewrite shows "↳ rewrite of r_7f3a · Informative · 300 words" (`ph-arrow-elbow-down-right`).
- **Providers**: `{role, name, url, modelLabel (Engines/Limits/Model), model, dev, unload}` for Search (SearXNG, `http://localhost:8888`, "duckduckgo, brave, arxiv", homelab, none), Fetch ("httpx + trafilatura", "in-process", "timeout 10s · 6 concurrent", desktop:cpu, none), Embeddings (Ollama, `http://localhost:11434`, `bge-small-en-v1.5`, desktop:gpu0, ollama), Scorer (llama.cpp server, `http://localhost:8081`, `bge-reranker-v2-m3-Q8_0.gguf`, desktop:gpu0, llama-swap), LLM (llama.cpp server, `http://localhost:8080/v1`, `qwen2.5-7b-instruct-q4_k_m.gguf`, desktop:gpu0, llama-swap). Health `{st: ok|degraded|down, ms, at, checking}` → "Healthy · 38 ms [· 41 tok/s]", "Slow · 1,840 ms (limit 1,000 ms)", "Unreachable · ECONNREFUSED", "Checking…", "just now" / "12 s ago" / "N min ago".
- **Profiles** `{id, desc, user?}` (the prototype also carries `th`, `scorer`, `gpuDev`, `cpuDev`):
  | id | desc | th | scorer | gpuDev | cpuDev |
  |---|---|---|---|---|---|
  | workstation | One GPU fits all models; models stay loaded. | .55 | jev | workstation:gpu0 | workstation:cpu |
  | low-vram | Models take turns on one small GPU; slower, fits 8 GB. | .60 | rerank | desktop:gpu0 | desktop:cpu |
  | cloud | Hosted APIs only; needs API keys. | .58 | rerank · hosted | cloud | cloud |
  | nixos (user) | SearXNG on homelab, models on desktop:gpu0. | .62 | jev | desktop:gpu0 | homelab |
- **GPU policy**: `shared` | `exclusive` (default exclusive).
- **Writing options** `{tone, custom, words, lang, cite, ref}`; defaults `{Objective, '', 1200, English, numeric, APA}`. Labels: Tone, Custom instructions, Length (words), Language, Citation marker, Reference style. Summary `Tone · N words · Lang · Cite · Ref`.
  - Tones: Objective (neutral and evidence-first), Formal (precise, impersonal register), Analytical (breaks the question into causes and factors), Persuasive (argues for a recommendation), Informative (a plain, broad overview), Explanatory (teaches how and why, step by step), Descriptive (a detailed account of what exists), Critical (weighs strengths, weaknesses and gaps), Comparative (sets the options side by side), Speculative (explores likely futures and open questions), Reflective (considers implications and trade-offs).
  - Languages: English, German, French, Spanish, Portuguese, Japanese, Chinese (Simplified).
  - Citation markers: `numeric` "[1] Numeric", `super` "¹ Superscript", `authoryear` "(Author, year)".
  - Reference styles: APA, MLA, Chicago, IEEE.
- **Run options**: recipe `report|context`, sources `web|files|both`, profile (ids above; default `low-vram`).
- **API tokens**: `{name, masked:'wosarcher_••••k9Qz', created:'Sep 12', last:'2 hours ago'|'Yesterday'|'Never'}`; new value `wosarcher_` + 36 base62 characters. Session: "Signed in on this browser since Oct 3, 09:12." Header text mentions `Authorization: Bearer <token>`.
- **Attachments**: `{name, bytes}` → `fmtB` (`B` / `KB`).
- **Copy JSON (context)** shape: `{run, parent, query, options:{recipe,sources,profile,writing:{…}}, passages:[{cite, score, source, heading_path:[…], text}]}`.
- **Help texts** (`HELP`; title, body, optional example):
  | key | title | body | example |
  |---|---|---|---|
  | `recipe` | Recipe | Report writes a cited report. Context stops after selecting passages and returns them with sources and scores, for agents or your own answer. Faster and cheaper. | |
  | `sources` | Sources | Web searches the internet. Files uses only your attachments. Both combines them; attachments get a share of the context budget. | |
  | `profile` | Profile | A named set of providers (search, fetch, embeddings, scorer, LLM) and GPU behavior. The list comes from the server. | |
  | `attach` | Attachments | Markdown or text files to research alongside the web, or instead of it. | pdf-ingest output (.md) |
  | `w-tone` | Tone | The writing style of the report. Each option in the list says what it emphasizes. | |
  | `w-custom` | Custom instructions | Extra guidance added on top of the tone. Set a default here, or change it for one run. | Focus on costs; avoid jargon. |
  | `w-words` | Length (words) | Target length of the report. The writer aims for it; it is not an exact count. | |
  | `w-lang` | Language | The language the report is written in. Sources can be in any language. | |
  | `w-cite` | Citation marker | How citations look in the text. | [1] · ¹ · (Leviathan et al., 2023) |
  | `w-ref` | Reference style | Format of the reference list at the end of the report: APA, MLA, Chicago or IEEE. | |
  | `overridden` | Overridden | This value differs from your default in Settings and applies to this run only. | |
  | `rwchanged` | Changed | This value differs from the version you are rewriting. | |
  | `ph-plan` | Plan | Splits your question into focused sub-queries for search. | |
  | `ph-search` | Search | Runs each sub-query against the search provider and collects candidate URLs. | |
  | `ph-fetch` | Fetch | Downloads each URL and extracts its readable text. Failed pages are skipped and the run continues. | |
  | `ph-load` | Load | Reads your attached files. | |
  | `ph-chunk` | Chunk | Splits pages and files into passages along their headings. | |
  | `ph-prefilter` | Prefilter | Quickly narrows chunks with embeddings or keyword ranking before the slower scorer. | |
  | `ph-score` | Score | Rates how useful each passage is for its question. | |
  | `ph-select` | Select | Picks the best passages that fit the writer's context budget. | |
  | `ph-write` | Write | Writes the report from the selected passages and cites each claim. | |
  | `wait` | Waiting for GPU | Another model is unloading from the same GPU. This stage starts when it is free. | |
  | `wait-score` | Score · waiting for GPU | Another model is unloading from the same GPU. This stage starts when it is free. Rates how useful each passage is for its question. | |
  | `device` | Device | The machine and GPU running the current stage, as labelled in the profile. | desktop:gpu0 |
  | `scorer` | Scorer | Which scorer ranked the passages. “fallback” means the configured scorer failed and a simpler one took over. | jev · rerank · bm25 · fallback |
  | `score` | Score and threshold | Each passage scores from 0 to 1. Passages right of the line are kept; the line is the scorer's configured threshold. | |
  | `rejected` | Rejected passages | Shows passages that scored below the threshold or did not fit the budget. | |
  | `tokens` | Tokens and cost | Prompt and completion tokens across all stages. Cost is $0 for local models. | |
  | `rewrite` | Rewrite | Writes a new version from the same passages with different writing options. No new search; it creates a linked version. | |
  | `retry` | Retry from Score | Reruns scoring, selection and writing on the saved pages. Useful after changing the scorer or profile. | |
  | `rerun` | Rerun | Starts a fresh run with the same question and attachments. | |
  | `versions` | Versions | Reports that share the same research. v1 is the original; rewrites follow. | |
  | `pdevice` | Device | Where this provider runs, as labelled in the profile. | |
  | `unload` | Unload | Whether the model can be released between phases: none, llama-swap or ollama. Exclusive GPU policy needs it. | |
  | `health` | Health | ok · degraded (slow, or cannot unload) · down · skipped (not used by this profile). | |
  | `gpupolicy` | GPU policy | Shared keeps all models loaded. Exclusive unloads a model before the next one on the same GPU loads; it needs unload support. | |
  | `wdefaults` | Writing defaults | Used for every new run. Each run can override them in its options. | |
  | `apitokens` | API tokens | For scripts and agents on other machines. A token is shown once, when you create it. | |
  | `h-recipe` | Recipe | Report wrote a cited report; context returned selected passages only. | |
  | `h-version` | Rewrite | A new version written from an earlier run's passages. It opens next to its parent as linked versions. | |
  | `h-cost` | Cost | Total for search and hosted APIs across all stages. $0 for local models. | |

  Composed entry `wait-<phase>` (used on a waiting phase card, e.g. `wait-score`): title "<Phase title> · waiting for GPU", body = `wait` body + " " + `ph-<phase>` body. An unknown key shows the key as the title with an empty body.

## 5. Interactions

- **Keyboard** (all disabled while locked):
  - Alt+1..4 switch screens (uses `e.code` Digit1-4).
  - Esc closes, in priority order: help tooltip, then Revoke dialog, then Rewrite dialog, then citation tooltip.
  - `R` toggles rejected passages on Live (ignored while typing).
  - `/` focuses the History search.
  - Ctrl/Cmd+Enter submits from the question box.
  - Enter or Space on the drop zone opens the file picker.
  - Going to New run focuses the textarea after 50ms.
- **Help**: one tooltip at a time, shared `#wa-help`.
  - Hover or focus on a help button opens it (unpinned), unless one is pinned.
  - Mouse leave or blur closes it after 140 ms, unless the pointer entered the tooltip (entering cancels the timer; leaving the tooltip restarts it). Pinned tooltips ignore leave and blur.
  - Click or tap pins it. A second tap on the same pinned button closes it; tapping another button pins that one instead.
  - A pointerdown outside any `[data-help]` element and the tooltip closes it. Any scroll (capture phase) closes it.
  - Escape closes help before dialogs and the citation tooltip.
- **Attachments**: click, drag-over (highlight) and drop; `.md`/`.txt` only. Others are skipped with the danger alert "Skipped x.pdf — only .md and .txt are supported." Duplicate names are ignored. Remove per file.
- **Options panel**: collapsed by default (`ph-caret-right`/`-down`, `aria-expanded`). Summary line shows run options and the writing summary. Badge "N overridden"; per-field Reset; "Reset all to defaults"; "edit defaults" links to Settings. Profile select updates the description line under it.
- **Live**:
  - Cancel (while running or connecting) freezes at the current t.
  - Open report (when done); Rerun (when failed or cancelled) starts a new run with the same inputs.
  - Retry from Score, Use cloud profile, Copy error (on failure).
  - Rejected toggle.
  - The Report panel auto-scrolls while writing if within 140px of the bottom.
- **Citation hover/focus**: shows the tooltip under the chip (or above it if fewer than 230px remain below); x = `clamp(left-20, 8, innerWidth-372)`. Hides on leave or blur. Works on both the Live and Report screens.
- **Report**:
  - Rewrite opens a dialog prefilled with the version's options. Changed fields get a "changed" tag and "was X". Footer: "Creates v2 linked to r_8c21". Confirm with "Rewrite from write stage". Backdrop click and Esc close it.
  - Confirming starts a rewrite run: earlier phases show "reused from r_xxxx", sources show "cached", the Phone tab moves to Report, and a recycle banner shows until writing starts. 400 words or fewer uses the short sample report.
  - Copy markdown, Download .md (`<id>.md` with `# query` prepended), Copy JSON. Each shows a toast.
  - Version buttons switch versions.
- **History**:
  - Search is a case-insensitive substring match on the query; Status and Recipe filters; Clear filters.
  - Opening a row goes to Report for completed runs, Live for the active run, and the failure/cancelled scenario otherwise.
  - Rerun; Delete shows the toast "Run deleted" with Undo (6s).
  - The current run is prepended as "Today, now".
- **Settings**:
  - Check (per provider, button disabled while checking) and Check all.
  - GPU policy seg switches Shared/Exclusive and updates the explanation.
  - Writing defaults autosave (prototype: localStorage `wosarcher-writing-defaults`) and flash "Saved" (`ph-check`, 1.5s). Changing a default also updates the New run value if it was not overridden.
  - Sign out locks the app.
  - Create token (form submit, disabled when the name is empty) shows the one-time reveal with Copy and Done. Revoke asks for confirmation, then shows a toast.
- **Login**: show/hide password; submit is disabled when the field is empty; 5 attempts, then a 30s pause with a live countdown (1s tick).
- **Theme toggle** (sidebar or phone bar).

## 6. Implementation notes

**Reuse directly**
- Nocturne `styles.css`: tokens (`--color-*` and ramps, `--space-*`, `--radius-*`, `--shadow-*`, fonts) and classes `.btn*`, `.tag*`, `.field`, `.input`, `.seg/.seg-opt`, `.card*`, `.elev-*`, `.table`, `.dialog*`. Base `h1..h6` sizes are overridden inline throughout.
- The `.sx` additions (muted/faint/line/mono/danger/warn/wa-ring, the light theme block, scrollbar, keyframes) should become a global app stylesheet.
- Note the light theme is a prototype addition; Nocturne itself is dark-only.
- The help button is repeated inline about 30 times; build it once as a component plus one shared tooltip.

**Prototype-only**
- support.js runtime: `<x-dc>`, `<helmet>`, `sc-if`/`sc-for`, `{{ }}`, `hint-placeholder-*`.
- The `data-props` scenario/speed/device switcher and the whole time simulation (`PH` s/r/e timings, `TF=3`, seq = t×27).
- The help spec page (`helpspec` screen and its static figures). In the source it is nested inside the Settings `sc-if`; it is a design reference, not an app screen.
- Each Run option row renders the help button twice; one is intended.
- The GPU policy seg keeps local state (`gpuPolicy`); the app shows the policy from the active profile, disabled.
- Hard-coded sample data: profiles (ids, descriptions, thresholds, scorers, devices), provider devices and unload values, fake health checks, client-side password `nocturne`, localStorage defaults.
- `style-hover="…"` and `style-before="…"` attributes are not implemented by support.js. Turn them into real `:hover` and `::before` CSS.
- Almost all styling is inline. Extract it to components or classes. Several values are computed in JS (status colours, phase state styles, help placement); move them to data-attribute or variant CSS where possible.
- Real implementation: a reducer over the event stream keyed by `seq`, reconnect with `?since=`, and the snapshot.
