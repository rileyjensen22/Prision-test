# Design direction (proposal)

**Feel.** The resident kiosk should feel like a well-run public library or an adult-education classroom: quiet, warm, plain-spoken, with generous space and large, honest controls. Nothing flashes, nothing is red unless it is truly urgent, and a lock is explained like a note from a librarian (what, why, until when, what you can do), never a greyed-out dead end. The staff dashboard is the opposite register: a dense, calm operations tool with strong typography, clear status, and almost no decoration.

The two surfaces share one set of tokens and one component library, with a resident theme and a staff theme.

## Layout (resident)

Landscape-first at 1280x800. Home becomes a two-pane screen that fits without scrolling at 1280x800:

- **Left pane (about 35%)**: tier ladder (1 to 10, current highlighted, ceiling marked if any), points to next tier, and "At Tier N+1 you unlock: ...".
- **Right pane**: large tiles in three groups (Everyday, Learning, Always available). A locked tile shows the lock icon, the plain reason and "until Fri 6:30 PM", and opens a "Why is this locked?" sheet with a single Appeal button.
- **Bottom bar** (fixed, in its own reserved space so it never covers content): Request staff, always visible.
- At 1024x600 and at large text, the panes stack and the content area scrolls inside the frame; the bottom bar still reserves its own space.

## Palette

Warm paper for day, a dimmed warm-dark for night. No pure white or pure black (less glare in a cell). All text pairs are at least AA, body text pairs are AAA (contrast ratios to be verified by script before building).

| Token | Day | Night (dim) | Use |
|---|---|---|---|
| `bg` | `#FBF8F2` | `#14181C` | page |
| `surface` | `#FFFFFF` | `#1D2328` | cards |
| `ink` | `#1B2430` | `#E8E3D8` | body text (AAA) |
| `ink-soft` | `#46505E` | `#B9B4A8` | secondary text (at least AA, still 20 px or larger) |
| `line` | `#CFC8BA` | `#3A434A` | borders |
| `primary` | `#0B5563` (deep teal) | `#7CC8D2` | main action, progress |
| `primary-ink` | `#FFFFFF` | `#0E1417` | text on primary |
| `ok` | `#1F6B4A` on `#E3F2E9` | `#8FD6AE` on `#1F3A2D` | open, completed |
| `lock` | `#3C4A7D` on `#E7EAF6` | `#AEBBF0` on `#252C4A` | locked: a calm slate-indigo, not red or amber |
| `notice` | `#7A4B00` on `#FFF1D0` | `#F0C674` on `#3A2E12` | needs attention, upcoming |
| `danger` | `#9B1C1C` | `#F2A0A0` | staff destructive actions only; never on the resident surface |

Staff theme: same tokens on a cooler neutral background (`#F4F6F8`), 1px borders instead of shadows. Status colours come with an icon and a text label every time.

## Type

- **Atkinson Hyperlegible** (designed by the Braille Institute for low vision; OFL license), self-hosted as woff2, Latin subset only (covers Spanish accents). Weights 400 and 700 only. One family for both surfaces; target under 60 kB total.
- Resident scale (px): small 20 (floor, never lower), body 22, label 24, h3 28, h2 34, h1 44, display 64. The "large" and "xlarge" settings multiply the scale by 1.25 and 1.5.
- Staff scale (px): 13 (dense table cells and metadata), 14 body, 16 section, 20 page title, 28 big-number.
- Line height 1.45 for body, 1.2 for headings. Left-aligned, no all-caps for sentences.

## Spacing, radius, shadow

- 4 px base: `1=4, 2=8, 3=12, 4=16, 6=24, 8=32, 12=48, 16=64`. Resident controls use at least 16 px padding and 16 px gaps between targets.
- Radius: resident 16 (cards) and 12 (buttons, inputs); staff 6.
- Shadow: one soft card shadow on the resident surface (`0 1px 2px` plus `0 4px 12px` at low alpha); none on staff (borders only). No blur or backdrop effects.
- Motion: 120 ms colour and opacity transitions only, turned off under `prefers-reduced-motion`.

## Icons and components

- **lucide** (ISC license), imported per icon so tree-shaking applies, and rendered inline from the bundle (no CDN). Icons are always paired with a text label.
- Components on **Radix primitives** (dialog, tabs, toggle, tooltip, select), styled with the shadcn/ui pattern (copied in, not a runtime dependency) plus `clsx` and `tailwind-merge`.
- Resident set: `Button` (min 64 px), `Tile`, `LockSheet`, `TierLadder`, `ProgressMeter`, `Banner` (offline, simulation), `EmptyState`, `ErrorState`, `ScreenFrame`.
- Staff set: `DataTable` (sortable, filterable, sticky header, row count), `StatusBadge` (icon plus text), `PendingBadge` (nav counts), `FilterBar`, `PageHeader`, `SimulationBanner` (sticky, high contrast, cannot be dismissed), `FormField`.

## Night mode

Switches on a schedule read from config (`night_mode_start` / `night_mode_end`, default 21:00 to 06:00). If the config key cannot reach the client without an API change, I will use the same default on the client and flag it. See the open question in the review message.

## Decisions I would like confirmed

1. Atkinson Hyperlegible for both surfaces.
2. The slate-indigo "lock" colour instead of amber or red.
3. The two-pane landscape home.
4. Day (light) is the default kiosk theme and dim night is scheduled. Today it is dark all the time.
