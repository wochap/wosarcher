# Design

## Context

The frontend implements the earlier prototype (removed from `design/`;
read at `git show 1b4ed9c:"design/project/Sift Research.dc.html"`) plus the
overrides in docs/design.md "Frontend decisions". A diff of that file
against the new `design/project/wosarcher.dc.html` (see proposal.md - Why)
shows that most of the new prototype's corrections are already built
(name, no version, 11 tones, 1200 words, the two citation controls,
threshold line from data, References from `report.json`, no VRAM). The
real gaps are:

| Area | Old prototype / current UI | New prototype |
|---|---|---|
| Help | none | `?` button + tooltip at ~38 places, `help` scenario, `--wa-ring` token, Escape closes help first |
| Run options | Recipe `context, report`; Profile segmented | Recipe `report, context`; Profile select `min(260px,100%)`, "(user profile)", description line |
| Writing labels | "Custom tone instructions", "Target length" | "Custom instructions", "Length (words)" |
| Tone | segmented | select, "<Tone> — <description>", `min(380px,100%)` |
| Reference style | select 220px | segmented APA/MLA/Chicago/IEEE |
| Language | select 220px | select `min(380px,100%)` |
| Custom placeholder | "e.g. Assume the reader knows CUDA. …" | "e.g. Focus on costs; avoid jargon." |
| Summaries | Tone · words · lang · marker | adds `· <reference style>` |
| "default:"/"was" custom text | full text | first 28 chars + "…" |
| Device chip | "<stage> · <device>", "· swapping models", "· idle", title | "<device>", "<device> · waiting", mono 11.5px, padding `4px 7px 4px 9px`, help, no title |
| Phase cards | `title`, label ellipsis, `minmax(0,1fr)` | no title, label `min-width:max-content`, `minmax(98px,1fr)` + `overflow-x:auto`, padding-bottom 2px, help |
| Passages header | title, summary, toggle | wraps (`gap 4px 8px`), scorer tag (neutral mono 10.5px), summary + "· ≥ th", three helps |
| Report | References `<h2>` only | "References" 19px + style name 12px muted + help; Rewrite and Versions helps |
| Settings profile line | "Profile **x** · devices …" (warn CPU icon) | "Active profile x(mono) [?] · description" (muted CPU 15px) |
| GPU policy | none | "GPU policy [?]" seg Shared/Exclusive + explanation |
| Provider card | Base URL, Model (72px labels) | + Device, Unload rows (84px labels), health help |
| History, Settings, footer, failure card, attachments | no help | help buttons |

Prototype-only differences not carried over: the `help` scenario page,
sample profiles (`nixos`) and per-profile thresholds/devices, sample
history text, the duplicated help button in the Run option rows (the
prototype renders two per row; one is intended), the GPU policy control's
local state.

## Goals / Non-Goals

**Goals:** one reusable help component; help texts in one module, verbatim;
the remaining visual and text gaps; the backend data the new UI shows.

**Non-Goals:** see proposal.md; also no tooltip library and no portal
library.

## Decisions

1. **One `HelpTip` button plus one shared popover.** `HelpTip` (button)
   takes a help key; `App` renders a single `HelpPopover` from UI state
   (`help: {key, rect, pinned} | null`) set through the UI context
   (`openHelp`, `closeHelp`). This matches the prototype's single
   `#wa-help` element, makes "only one open" structural, and lets the
   popover use the fixed-position math once. Alternative: each button owns
   its popover; rejected, it needs cross-instance coordination for
   one-open and outside-tap.
2. **Help texts in `web/src/components/help.ts`** as a typed record keyed
   by the prototype's keys (`recipe`, `w-tone`, `ph-score`, `h-cost`, …)
   with `{title, body, example?}`, plus `helpFor(key)` that builds the
   `wait-<phase>` and `retry-<stage>` entries. A unit test pins every text
   to the prototype (copied strings). Keys mirror the prototype so the
   inventory and the code read the same.
3. **Placement math is a pure function** `placeHelp(rect, viewport)` →
   `{x, y, below, arrowX}` with the prototype's constants (W 272, 8px
   margin, 180px rule, 9px gap, arrow clamp 10..252). Tested without a DOM.
4. **Escape order** uses the existing overlay stack: new `OverlayKind`
   `"help"` first in `PRIORITY`. The popover registers itself while open.
   Outside-press uses one `pointerdown` listener on `document` and scroll
   uses one capturing `scroll` listener, both only while a tooltip is open.
5. **Hover-out delay of 140 ms** in the popover state, cancelled when the
   pointer enters the popover, as the prototype.
6. **Profile descriptions are file metadata, not settings.** `config.py`
   removes the top-level `description` from the profile data in
   `load_profile` before validation (Settings forbids extra keys) and
   `profile_description(path, data)` returns it (ConfigError when not a
   string). `list_profiles` stays as is; callers that need the description
   load the profile. Alternative: a `Settings.description` field; rejected,
   it would show in `profile show`, `request.json`, and accept `--set`.
7. **GPU policy and unload method come from the doctor.** `DoctorReport`
   gains `gpu_policy`, `ProviderHealth` gains `release`; `meta.py` copies
   them into `HealthReport.gpu_policy` and `ProviderCheck.release`. The
   Settings screen already depends on the health report, so no new
   endpoint. The GPU policy segmented control is shown disabled (decision
   recorded in docs/design.md "Frontend decisions"): the policy is part of
   the profile.
8. **Scorer tag** reads the first `passages.scored` scorer that is not
   `passthrough`; "fallback" is computed by comparing with
   `detail.request.settings.score.provider` (already in `RunDetail`).
9. **Prefilter card title** depends on the provider (`embeddings` →
   "Embeddings", else "Prefilter"), refining the role map that
   `ui-run-state-fixes` introduces.

## Risks / Trade-offs

- [Two edits of the built-in profiles and the doctor in one pipeline
  (`provider-wire-formats`)] → this change is applied after it; tasks add
  only the `description` line and the two new fields.
- [Help buttons inside `<label>`-like rows could steal label clicks] → the
  button sits next to the `<label>`, never inside it.
- [Per-query thresholds differ for `rerank`] → "≥ th" is shown only when
  all scored queries share one threshold.
- [Tooltip under a dialog] → popover z-index 35 sits above dialogs (20)
  and the citation tooltip (30), below sign-in (40), as the prototype.
