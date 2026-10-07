# Nocturne design system

Nocturne is a quiet, compact interface on the Catppuccin palette (Mocha dark, Latte light): Inter at medium weight, soft 8px radii and an accent used as a line and a glow rather than a flood. Rules fade to transparent at their ends — over 48px a side — rather than stopping cleanly; short accent marks stay solid. Contrast comes from the tonal ramps, not from saturation, and photographs blend into the page with their dark values falling away.

## How to use this

- Link the one stylesheet from every page — `<link rel="stylesheet" href="styles.css">` (adjust the relative path) — and take every color, font, spacing, radius and shadow from its variables (`var(--color-*)`, `var(--font-*)`, `var(--space-*)`, `var(--radius-*)`, `var(--shadow-*)`). Never hard-code a hex, a font name or a px value the tokens already carry.
- Build with the classes below rather than inventing parallel ones; the component pages are plain HTML, so view source and copy the markup.
- `templates/` holds starting points a consuming project can copy whole.
- The whole system was derived from `theme.json`. To change the look, edit the tokens at the top of `styles.css` — every page, the thumbnail and this guide read from them — and keep `theme.json` and the written guidance in step so they don't drift from what the CSS actually does.

## Direction

Left-aligned, asymmetric layouts. Flush-left headings; content hugs the left edge with whitespace on the right. Buttons are outlined (1px accent border on transparent), not solid-filled. In decks, section dividers lift to a saturated deep-indigo ground (the `--color-section` tokens — saturation as presence, at slide scale), and the landing template's one full-bleed stat band makes the same presence move at page scale; everywhere else grounds stay desaturated, with soft gradient depth rather than flat fills. Wrap hero and inline images in the `.lighten` class — `mix-blend-mode: lighten` blends them into whatever the page paints behind them: anything darker than the backdrop falls away, so on a dark page a black photo background disappears entirely. Prefer photographs shot on dark or black backgrounds.

## Color

Catppuccin — **Mocha** is the dark default (`:root` in `styles.css`); **Latte** is the light flavor, applied by consuming pages as an override of the same tokens. Every color is a Catppuccin hex or a `color-mix()` of two; no ad-hoc values.

Roles (Mocha / Latte): `--color-bg` base (#1e1e2e / #eff1f5) is the page ground; `--color-surface` surface0 (#313244) for raised surfaces — on Latte a 30% base→surface0 mix, because full surface0 can't carry colored text at 4.5:1; `--color-mantle` for sidebars and sunken panels; `--color-crust` for the deepest layer (code, terminals). `--color-text` text (#cdd6f4 / #4c4f69). `--color-accent` mauve (#cba6f7 / #8839ef) — still a line, a glow and a mark, never a flood; primary buttons stay outlined. `--color-divider` surface1. Danger is red (Latte: red mixed 20% toward text); warn is yellow on Mocha, and on Latte peach mixed 70% toward text, since neither yellow nor peach reaches 4.5:1 on the light ground. The `--color-accent-2-*` set mirrors the accent (mono scheme).

The neutral ramp maps 100 → 900 from text to ground: text, subtext1, subtext0, overlay2, overlay1, overlay0, surface2, surface1, surface0 — identical names in both flavors, so it flips automatically. Catppuccin has no tonal ramps, so the accent ramp is derived: 500 is mauve, 100–400 mix it 80/60/40/20% toward text, 600–900 mix it 20/40/60/80% toward the ground. Use 700–900 for tinted fills and hovers, 500 as the base, 100–300 for text on tints and pressed states (`--color-accent-300` for accent-colored body text). Elevation (`--shadow-sm/md/lg`) is a surface1 / surface2 / overlay0 ring plus ambient shade — black on Mocha, Latte text (rgba(76,79,105)) on Latte.

## Type

Inter for headings over Inter for body text, loaded as `--font-heading` / `--font-body`. Density 0.70× and radius 8px are already baked into the `--space-*` / `--radius-*` scales — use the variables, not raw numbers.

## Icons

Use Phosphor icons (https://phosphoricons.com) throughout.

## Interaction states

Interactive states are themed, never browser defaults: give every interactive element a `:hover` tint and a pressed state from the accent ramp (one step past the base — `--color-accent-600` on a light ground, `--color-accent-400` on a dark one, or a `color-mix()` tint for outlined/ghost variants), and style keyboard focus with `:focus-visible { outline: 2px solid var(--color-accent); outline-offset: 2px; }` — never leave the default blue focus ring.

## Components

| Class | What it is | Shown in |
| --- | --- | --- |
| `.btn` with `.btn-primary`, `.btn-secondary`, `.btn-ghost`, `.btn-icon`, `.btn-block` | Actions — the primary is an accent outline, never a fill | components/buttons.html |
| `.tag` with `.tag-accent`, `.tag-accent-2`, `.tag-neutral`, `.tag-outline` | Small labels tinted from the ramps (mono palette: accent-2 reads the same as accent) | components/buttons.html |
| `.field` + `label`, `.input`, `.radio` + `.dot`, `.seg` + `.seg-opt` | Form fields and choices on native elements — no script | components/forms.html |
| `.card` with `.card-kicker`, `.card-title`, `.card-body`, `.card-meta`; `.elev-sm/md/lg` | Surface-filled content cards; elevation utilities | components/cards.html |
| `.nav` + `.nav-brand` | The header bar | components/navigation.html |
| `.table` | Data tables with themed header and row rules | components/table.html |
| `.dialog-backdrop` + `.dialog` (+ `.dialog-title/-body/-actions`) | A modal at the top elevation | components/dialog.html |
| `.hr` | A horizontal rule — present, but this system prefers whitespace; avoid it | — |
| `.lighten` | The image wrapper — every content photograph goes through it | foundations/image.html |

States are built in: hovers and pressed states come from the accent ramp, keyboard focus is the 2px accent `:focus-visible` ring, `::selection` is an accent tint, and disabled controls drop to 45% opacity. Don't restyle them per page. The accent-to-ground pair is tuned to at least 3:1 — enough for icons, large text and interface chrome, not for body copy — so for paragraph-size text in the accent use a deep ramp step (`--color-accent-300` on this ground) rather than the accent itself.

## Do

- Keep chroma low outside the accent; lean on the `--color-neutral-*` steps for surfaces, borders and muted text.
- Use the compact spacing scale (density 0.7×) — this system is dense on purpose.
- Outline primary actions and let `:focus-visible` carry the accent.
- Put photographs through the `.lighten` wrapper and prefer subjects shot on dark backgrounds.

## Don't

- Do not flood large areas with the accent or any saturated fill — the exceptions are the deck section-divider ground and the landing template's stat band (both `--color-section`), saturated fields carried as presence (the accent carries its chroma in lines and marks, never as a flood).
- Do not use pure black or pure white — every value comes from the ramps. (Shade is the exception, as in the shadow tokens: ambient darkness mixed from black is a shadow, not a color.)
- Do not stack heavy shadows; on a dark ground elevation is an edge plus ambient darkness.
- Do not bolden headings past their 500 weight — hierarchy here is size and space.

## Files

- `styles.css` — the only stylesheet: the token sheet (`:root` variables, ramps, base type) plus the component layer. Link it from every page.
- `readme.md` — this guide.
- `theme.json` — the parameters these files were derived from (a machine-readable record of the theme).
- `thumbnail.html` — the project cover (brand mark + swatches).
- `foundations/type.html` — the type scale and the heading/body pairing at real sizes.
- `foundations/color.html` — color roles and the 100-900 tonal ramps, with usage notes.
- `foundations/layout.html` — the spacing scale, the grid and how edges are drawn.
- `foundations/icons.html` — the icon set at interface sizes, inline and in buttons.
- `foundations/image.html` — how photographs and figures are treated.
- `components/buttons.html` — buttons, icon buttons and tags in every variant and state.
- `components/forms.html` — text fields, radios and the segmented control on native elements.
- `components/cards.html` — content cards and the elevation steps.
- `components/navigation.html` — the header bar pattern.
- `components/table.html` — a data table with the themed header and row rules.
- `components/dialog.html` — a modal over its backdrop at the top elevation.
- `theme.html` — the theme's parameters rendered as a reference sheet.
- `templates/landing/` — a starter page consuming the system the intended way (`index.html`, its `ds-base.js` loader, and the vendored `image-slot.js` its photograph mounts).
- `assets/photo.jpg` — the reference photograph the imagery page treats.
