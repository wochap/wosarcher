# Proposal: design-refresh

## Why

The Claude Design bundle was re-exported (commit 1b4ed9c) with a new
primary prototype, `design/project/wosarcher.dc.html`. It replaces the earlier prototype
(removed from the bundle; still readable in git at commit 1b4ed9c), which
the frontend implements today. The new prototype adds inline help (a `?` button with a tooltip
after about 38 non-obvious labels and column headers, plus a `help`
scenario that specifies the component) and folds in the product decisions
the frontend already applies (name wosarcher with no version, the 11
tones, 1200 words, two citation controls, device labels without VRAM, the
threshold line from data). It also changes several controls and texts
(tone as a described select, reference style as a segmented control,
profile as a select with a description line from the server, a scorer tag
and threshold in the Passages header, Device and Unload rows and a GPU
policy line in Settings, a References heading with its style). The UI and
the docs must follow the new file, and the server must provide the data
it shows (profile descriptions, provider unload method, GPU policy).

## What Changes

- **Design source**: every reference to the old prototype (docs/design.md
  "Frontend design", openspec/config.yaml, the web-shell spec,
  `web/src/vendor/prototype.css`) moves to `design/project/wosarcher.dc.html`;
  docs/frontend-inventory.md is regenerated to describe only the new
  prototype.
- **Inline help**: a reusable help button and tooltip exactly as the
  prototype's `help` scenario specifies (16px muted `question` icon with a
  28px hit area; hover or focus opens it on desktop, a tap pins it open;
  one open at a time; closes on leaving, tapping outside, scrolling, or
  Escape, which now closes help first; opens below, or above and shifted
  to stay 8px inside the viewport; arrow pointing at the button;
  `role="tooltip"` linked by `aria-describedby`), with every placement and
  text of the prototype, verbatim.
- **New run options**: Recipe lists `report` before `context`; Profile is
  a select of the server's profiles (user profiles marked "(user
  profile)") with the selected profile's description under it.
- **Writing fields** (New run, Rewrite dialog, Settings): labels "Custom
  instructions" and "Length (words)"; Tone is a select whose options read
  "Objective — neutral and evidence-first" and so on; Reference style is a
  segmented control (APA, MLA, Chicago, IEEE); Language is a wider select;
  new placeholder; summaries ("Options" header, "Written with" line) add
  the reference style; long custom instructions are shortened in
  "default:" and "was" texts.
- **Live run**: device chip shows only the device label ("<device>",
  "<device> · waiting"), in mono; phase cards lose their title tooltip,
  never truncate their label, and scroll sideways when narrow; the
  Passages header shows a scorer tag ("fallback" when the configured
  scorer failed) and "≥ <threshold>" after the summary.
- **Report**: a "References" heading with the reference style name.
- **Settings**: profile line "Active profile <name> · <description>"; a
  GPU policy line (Shared or Exclusive, showing the checked profile's
  `run.gpu_policy`, with its explanation); provider cards gain Device and
  Unload rows.
- **Backend**: profile TOML files accept an optional top-level
  `description` string (built-in profiles get one-line descriptions; user
  profiles may set one); `GET /api/profiles` returns it and
  `wosarcher profile list` prints it. `wosarcher doctor --json` and
  `GET /api/providers/health` also report each provider's `release` and
  the profile's `gpu_policy`.
- docs/design.md "Frontend design", "Frontend decisions", "Server",
  "Configuration", and "Switching providers without a rebuild" updated.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `web-shell`: "Design source and name" (new prototype file), "Styling
  uses the design system" (`--wa-ring` token), "Keyboard shortcuts"
  (Escape closes help first), "Settings providers" (profile line, GPU
  policy, Device and Unload rows; builds on the role names from
  `ui-run-state-fixes`), "Writing defaults" (field labels and controls);
  new "Inline help" and "Shell help placements".
- `web-run`: "Run options" (recipe order, profile select and
  description), "Writing overrides" (labels, controls, summary), "Device
  chip" (label only), "Phase timeline" (no title, full label, sideways
  scroll), "Passages panel" (scorer tag, threshold in the summary),
  "Report screen" ("Written with" line, References heading); new "Run
  help placements".
- `run-config`: "Profiles" (optional `description`), "Profile commands"
  (`profile list` prints it).
- `http-api`: "Profiles" (`description`), "Provider health" (`release`,
  `gpu_policy`).
- `provider-doctor`: new "Doctor reports release and GPU policy".

## Non-goals

- The prototype's `help` scenario page ("Inline help" spec sheet) is not
  built as a screen; it specifies the component.
- Changing the GPU policy from the browser: the prototype's control is
  local state, and the policy lives in the profile (`run.gpu_policy`).
  The UI shows the checked profile's policy; to change it, edit the
  profile.
- Sample data of the prototype (profile ids `nixos`, devices such as
  `desktop:gpu0`, thresholds per profile, sample history notes) is not
  copied; real data comes from the API.
- Run-state, Cancel, reconnect, not-found, and provider role-name fixes:
  change `ui-run-state-fixes`, which this change builds on.

## Impact

- Frontend: new `web/src/components/HelpTip.tsx` (+ CSS, test) and
  `web/src/components/help.ts`; `web/src/app/{context.ts,keys.ts,App.tsx}`
  (help overlay); `web/src/vendor/prototype.css`;
  `web/src/components/{WritingOptionsForm,WritingControl,tones}.ts(x)`;
  `web/src/run/format.ts`; `web/src/screens/new/{Attachments,OptionsPanel,NewRunScreen}.tsx`;
  `web/src/screens/live/{DeviceChip,LiveHeader,PhaseTimeline,PassagesPanel,FailureCard,LiveFooter}.tsx`;
  `web/src/screens/report/{ReportScreen,VersionsNav}.tsx`,
  `web/src/run/ReportMarkdown.tsx`;
  `web/src/screens/history/HistoryTable.tsx`;
  `web/src/screens/settings/{ProvidersSection,WritingDefaults,TokensPanel}.tsx`;
  fixtures and `fakeApi`; regenerated `web/src/api/generated.ts`.
- Backend: `src/wosarcher/config.py` (description), the three built-in
  profiles, `src/wosarcher/cli/__init__.py` (`profile list`),
  `src/wosarcher/models.py` (`ProfileInfo.description`,
  `ProviderHealth.release`, `DoctorReport.gpu_policy`,
  `ProviderCheck.release`, `HealthReport.gpu_policy`),
  `src/wosarcher/doctor.py`, `src/wosarcher/server/meta.py`; tests in
  `tests/test_config.py`, `tests/test_cli_doctor.py`, `tests/server/test_meta.py`,
  and a `profile list` test.
- Docs: docs/design.md, docs/frontend-inventory.md, openspec/config.yaml.
- Depends on `ui-run-state-fixes` (ProvidersSection role names, LiveHeader
  Cancel rules) and `provider-wire-formats` (edits the same built-in
  profiles and the doctor); applied after both.
