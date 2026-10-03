# Spec Delta

## MODIFIED Requirements

### Requirement: Design source and name
Every screen and state SHALL match `design/project/wosarcher.dc.html`
(the "prototype") in layout, sizes, colors, icons, and text, in the dark
and light themes and in the desktop and phone layouts, except where
docs/design.md "Frontend decisions" overrides it. The product name SHALL be
"wosarcher" everywhere, including the brand, the API token prefix shown in
the UI, and browser storage keys. No version string SHALL be hard-coded.
The prototype's `help` scenario specifies the inline help component and
is not a screen of the app.

#### Scenario: Brand in the sidebar
- **WHEN** the app is open on a desktop-width window (any prototype scenario, for example `new`)
- **THEN** the sidebar brand row shows the funnel icon and "wosarcher" with no version string, and the word "Sift" appears nowhere in the UI

### Requirement: Styling uses the design system
Colors, fonts, radii, and shadows SHALL come from the vendored Nocturne
stylesheet and the vendored prototype additions (`--wa-ring`, `--muted`,
`--faint`, `--line`, `--mono`, `--color-danger`, `--color-warn`, the light
theme block, the scrollbar style, and the keyframes `sx-spin`, `sx-pulse`,
`sx-blink`, `sx-shimmer`). `--wa-ring` SHALL be `#9397ab` in the dark
theme and `#c9cddd` in the light theme. Application stylesheets outside
the vendored directory SHALL contain no raw hex colors and no font family
other than a Nocturne or prototype font variable. The UI SHALL NOT use
Tailwind or a third-party component library.

#### Scenario: Token check
- **WHEN** an application stylesheet outside `web/src/vendor/` contains a raw hex color
- **THEN** `scripts/check` fails and names the file and line

#### Scenario: Help arrow ring in both themes
- **WHEN** a help tooltip is open in the light theme (prototype `help` scenario, figure B, `theme=light`)
- **THEN** its arrow's border uses `--wa-ring`, which resolves to `#c9cddd`

### Requirement: Keyboard shortcuts
Alt+1 to Alt+4 SHALL switch to New run, Live run, History, and Settings
(by physical key, so they work on any keyboard layout). Escape SHALL close,
in this order, an open help tooltip, then the open confirmation dialog,
then the open form dialog, then an open citation tooltip; one press closes
only the first of these that is open. `/` SHALL focus the History search
when the History screen is shown and focus is not in a text field. While
the sign-in screen is shown, no shortcut SHALL act.

#### Scenario: Switch screens
- **WHEN** the user presses Alt+3 outside a text field
- **THEN** the Run history screen is shown

#### Scenario: Locked
- **WHEN** the sign-in screen is shown and the user presses Alt+4
- **THEN** nothing changes

#### Scenario: Help closes before the dialog
- **WHEN** the Rewrite dialog is open with the help tooltip of its Tone field open, and the user presses Escape
- **THEN** the help tooltip closes and the dialog stays open; a second Escape closes the dialog

### Requirement: Settings providers
The Settings screen of the prototype (no dedicated scenario; reached with
Alt+4 from any scenario) SHALL show the H1 "Settings" with a "Check all
providers" button, the profile line, the GPU policy line, and a
"Providers" grid with one card per configured provider block from
`GET /api/providers/health`, in the order the server lists them, titled
by role: `search` "Search", `fetch` "Fetch", `prefilter` "Embeddings" when
its provider is `embeddings` and "Prefilter" otherwise (for example `bm25`
or `none`), `score` "Scorer", `llm` "LLM" (any other block name
capitalised). Each card SHALL show the provider name and a list with
the prototype's 84px label column: Base URL, Model, Device (the device
label, or "–"), and Unload (`none`, `llama-swap`, or `ollama`, the
provider's `release`). Each card's health strip SHALL show the last
result: `ok` as "Healthy · N ms", `degraded` as "Slow · N ms" with the
detail, `down` as "Unreachable · <detail>", and `skipped` as "Skipped ·
<detail>", with the matching prototype icon and tint, and how long ago the
result arrived. The server checks all providers of the profile at once, so
"Check" on a card and "Check all providers" SHALL both run one health
request; while it runs, the cards SHALL show "Checking…" with the spinning
dashed circle and the Check buttons SHALL be disabled.

The profile line SHALL read "Active profile <name> · <description>" with
the muted CPU icon, the name in the mono font, and the description of
that profile from `GET /api/profiles`; the name is the profile of the last
health result (the active profile before the first result), and " ·
<description>" is left out when the description is empty. The GPU policy
line SHALL show "GPU policy", a segmented control with Shared and
Exclusive in which the health result's `gpu_policy` is selected and both
options are disabled, and the text "Each model unloads before the next
one loads on <devices>." for exclusive or "All models stay loaded on
<devices>." for shared, where <devices> are the distinct device labels of
the `prefilter`, `score`, and `llm` providers joined with ", " (without
" on <devices>" when none has a device label). Secrets SHALL never be
shown.

#### Scenario: Slow provider
- **WHEN** the health result for search is `degraded` at 1,840 ms
- **THEN** the Search card shows the warn icon and "Slow · 1,840 ms" on the warn tint

#### Scenario: Check all
- **WHEN** the user presses "Check all providers"
- **THEN** every card shows "Checking…" until the new results arrive

#### Scenario: Server block names
- **WHEN** the health report lists the blocks `search`, `fetch`, `prefilter` (provider `embeddings`), `score`, and `llm`
- **THEN** the cards are titled Search, Fetch, Embeddings, Scorer, and LLM, and no card shows `prefilter` or `score` as its title

#### Scenario: Keyword prefilter
- **WHEN** the `prefilter` block's provider is `bm25`
- **THEN** its card is titled "Prefilter" and shows `bm25` as the provider name, never "Embeddings"

#### Scenario: Profile line with description
- **WHEN** the checked profile is `low-vram` and `GET /api/profiles` describes it as "Models take turns on one small GPU; slower, fits 8 GB."
- **THEN** the line reads "Active profile low-vram · Models take turns on one small GPU; slower, fits 8 GB." as in the prototype's Settings screen

#### Scenario: Exclusive policy
- **WHEN** the health result has `gpu_policy` `exclusive` and the prefilter, score, and llm providers all use device `desktop:gpu0`
- **THEN** Exclusive is selected, neither option can be changed, and the text reads "Each model unloads before the next one loads on desktop:gpu0."

#### Scenario: Device and Unload rows
- **WHEN** the score provider has device `desktop:gpu0` and release `llama-swap`
- **THEN** the Scorer card lists Device `desktop:gpu0` and Unload `llama-swap`

### Requirement: Writing defaults
The Settings screen SHALL show the "Writing defaults" panel with the
prototype's fields, in this order: Tone (a select whose options read
"<Tone> — <description>" for the 11 tones Objective "neutral and
evidence-first", Formal "precise, impersonal register", Analytical "breaks
the question into causes and factors", Persuasive "argues for a
recommendation", Informative "a plain, broad overview", Explanatory
"teaches how and why, step by step", Descriptive "a detailed account of
what exists", Critical "weighs strengths, weaknesses and gaps",
Comparative "sets the options side by side", Speculative "explores likely
futures and open questions", Reflective "considers implications and
trade-offs"; a saved tone not in the list is offered as itself), Custom
instructions (a textarea with the placeholder "e.g. Focus on costs; avoid
jargon."), Length (words) (100 to 4000, step 50, "words, approximately"),
Language (a select), Citation marker (segmented: "[1] Numeric",
"¹ Superscript", "(Author, year)"), and Reference style (segmented: APA,
MLA, Chicago, IEEE). Selects SHALL be `min(380px, 100%)` wide. Values SHALL
be loaded from `GET /api/settings`. Each change SHALL be saved with
`PUT /api/settings` without a save button, and a "Saved" mark with a check
SHALL show for 1.5 seconds after the server accepts it. When the server
rejects a value, the field SHALL show the server's error and the previous
value SHALL be restored. The same fields, labels, and controls SHALL be
used by the New run Options panel and the Rewrite dialog.

#### Scenario: Autosave
- **WHEN** the user changes Length (words) to 800
- **THEN** `PUT /api/settings` is sent with `words` 800 and "Saved" appears

#### Scenario: Rejected value
- **WHEN** the server rejects a change
- **THEN** the field shows the error and the earlier value is shown again

#### Scenario: Tone select
- **WHEN** the Settings screen shows the default tone `objective`
- **THEN** the Tone select shows "Objective — neutral and evidence-first" and lists the 11 tones with their descriptions

#### Scenario: Reference style as segments
- **WHEN** the user picks MLA in Reference style
- **THEN** `PUT /api/settings` is sent with `reference_style` "MLA"

## ADDED Requirements

### Requirement: Inline help
The UI SHALL offer the prototype's inline help (scenario `help`, figures A
to D): a help button placed 4 to 5px after a label or column header, 16px
round, transparent, with the Phosphor `question` icon at 15px in the
`--faint` color, `cursor: help`, an invisible hit area 6px larger on every
side (28px), and the accessible label "Help: <title>". Hovering it SHALL
show the text color on an 8% text-color tint; keyboard focus SHALL show
the Nocturne focus ring; while its tooltip is pinned open it SHALL show
the accent-300 color on a 22% accent tint.

The tooltip SHALL be one element with `role="tooltip"` referenced by the
button's `aria-describedby`, fixed-positioned above every other overlay
except the sign-in screen, 272px wide (at most the viewport width minus
16px), with padding 9px 12px 10px, the medium radius, the surface
background, the large shadow, 13px text at line height 1.45 in normal
weight, case, and letter spacing whatever its container uses, showing the
title (weight 600), the body, and, when the entry has one, "Example: "
(12px, muted) followed by the example in the mono font at 11.5px.

Placement: horizontally centred on the button and clamped to stay 8px
inside the viewport; below the button (9px gap) when more than 180px
remain below it or less than 180px remain above it, otherwise above it
(9px gap). A 10px square arrow rotated 45° SHALL point at the button's
centre (clamped to 10px from either end), on the top edge with a 1px
`--wa-ring` border on its top and left sides when below, and on the bottom
edge with the border on its bottom and right sides when above.

Behavior: at most one tooltip SHALL be open. Pointer hover or keyboard
focus SHALL open it; leaving or blurring SHALL close it after 140 ms
unless the pointer has entered the tooltip. A click or tap SHALL open it
pinned: a pinned tooltip ignores hover and blur, a second tap on the same
button closes it, and a tap on another help button pins that one instead.
A pointer press outside every help button and the tooltip, any scroll,
or Escape SHALL close it.

#### Scenario: Hover open (figure B)
- **WHEN** the user hovers the help button after "Recipe" on the New run screen
- **THEN** a tooltip titled "Recipe" opens 9px below the button with its arrow pointing at the button, and it closes 140 ms after the pointer leaves the button without entering the tooltip

#### Scenario: Keyboard focus
- **WHEN** the user tabs to a help button
- **THEN** the button shows the focus ring, the tooltip opens, and the button's `aria-describedby` names the tooltip

#### Scenario: Phone tap (figure C)
- **WHEN** on a 390px wide window the user taps the help button after "Profile"
- **THEN** the tooltip opens pinned and stays open until the user taps outside it, taps the same button again, scrolls, or presses Escape

#### Scenario: Near an edge, flipped (figure D)
- **WHEN** a help button sits 20px from the right edge and 30px from the bottom of the viewport and its tooltip opens
- **THEN** the tooltip opens above the button, its right edge is 8px inside the viewport, and the arrow on its bottom edge points at the button

#### Scenario: Example line
- **WHEN** the Attachments help opens
- **THEN** the tooltip shows "Attachments", "Markdown or text files to research alongside the web, or instead of it.", and "Example: pdf-ingest output (.md)"

#### Scenario: Only one open
- **WHEN** one help tooltip is pinned open and the user taps another help button
- **THEN** only the second tooltip is open

### Requirement: Shell help placements
The Settings and Run history screens SHALL place help buttons where the
prototype places them, with these titles and bodies verbatim (the
accessible label is "Help: <label>"):

| Placement | Label | Title | Body |
|---|---|---|---|
| Settings profile line, after the profile name | Profile | Profile | A named set of providers (search, fetch, embeddings, scorer, LLM) and GPU behavior. The list comes from the server. |
| After "GPU policy" | GPU policy | GPU policy | Shared keeps all models loaded. Exclusive unloads a model before the next one on the same GPU loads; it needs unload support. |
| Provider card, after "Device" | Device | Device | Where this provider runs, as labelled in the profile. |
| Provider card, after "Unload" | Unload | Unload | Whether the model can be released between phases: none, llama-swap or ollama. Exclusive GPU policy needs it. |
| Provider card health strip, after the health text | Health | Health | ok · degraded (slow, or cannot unload) · down · skipped (not used by this profile). |
| After the "Writing defaults" heading | Writing defaults | Writing defaults | Used for every new run. Each run can override them in its options. |
| After "API tokens" in the Security panel | API tokens | API tokens | For scripts and agents on other machines. A token is shown once, when you create it. |
| History table header, after "Recipe" | Recipe | Recipe | Report wrote a cited report; context returned selected passages only. |
| History table header, after "Cost" | Cost | Cost | Total for search and hosted APIs across all stages. $0 for local models. |
| History rewrite note, after the writing changes | Rewrite marker | Rewrite | A new version written from an earlier run's passages. It opens next to its parent as linked versions. |

Every writing field label (Settings, New run, Rewrite dialog) SHALL be
followed by a help button with these entries:

| Label | Title | Body | Example |
|---|---|---|---|
| Tone | Tone | The writing style of the report. Each option in the list says what it emphasizes. | |
| Custom instructions | Custom instructions | Extra guidance added on top of the tone. Set a default here, or change it for one run. | Focus on costs; avoid jargon. |
| Length (words) | Length (words) | Target length of the report. The writer aims for it; it is not an exact count. | |
| Language | Language | The language the report is written in. Sources can be in any language. | |
| Citation marker | Citation marker | How citations look in the text. | [1] · ¹ · (Leviathan et al., 2023) |
| Reference style | Reference style | Format of the reference list at the end of the report: APA, MLA, Chicago or IEEE. | |

#### Scenario: Health help on a card
- **WHEN** the user hovers the help button in the Scorer card's health strip
- **THEN** the tooltip reads "Health" and "ok · degraded (slow, or cannot unload) · down · skipped (not used by this profile)."

#### Scenario: Help in an uppercase header
- **WHEN** the user opens the help after the History table's "Cost" header
- **THEN** the tooltip text is in normal case and weight, not the header's style

#### Scenario: Writing field help in Settings
- **WHEN** the user focuses the help button after "Citation marker" in Writing defaults
- **THEN** the tooltip shows "How citations look in the text." and "Example: [1] · ¹ · (Leviathan et al., 2023)"
