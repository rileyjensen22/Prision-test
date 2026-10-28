# UI audit (before)

Screenshots are in `docs/ui/before/`. They were captured from the real e2e build (synthetic data) by `web/ui-audit/shoot.mjs`.

- **Resident**: 18 screens. The primary screens (home, locks, why-locked, tier, education, commissary, calls) are shot at 1280x800, 1024x600 and 1920x1080, in English and Spanish, at normal and large text. Secondary screens are shot at 1280x800 only (English normal, and Spanish at both text sizes).
- **Staff**: login plus 19 pages at the three sizes. Staff has no language or text-size setting (see S1).
- Filenames: `<screen>__<lang>__<text size>__<viewport>.png` for resident, `<page>__<viewport>.png` for staff.

Baseline bundle (`npm run build`): JS 509.85 kB (148.44 kB gzip), CSS 13.43 kB (3.49 kB gzip). Vite already warns about the single 500 kB chunk.

## Resident kiosk

| # | Problem | Where | Why it matters |
|---|---|---|---|
| R1 | **Portrait layout on a landscape device.** Every screen is one ~600 to 720 px column centred in 1280 px. Roughly half the screen is empty and the home page scrolls to about 2000 px. | All | Wall-mounted touch screen; scrolling a long page is the hardest interaction for first-time users. |
| R2 | **No hierarchy on home.** Tier, restrictions, limits, 8 service tiles, optional links and 10 baseline tiles are stacked with equal weight. There is no single primary action. | Home | Brief: one primary action per screen. |
| R3 | **Text below the 20 px floor.** Tile titles, lock reasons ("Unlocks at Tier 4"), "Disruptive behavior" and category labels render at about 14 to 16 px. Only "Open"/"Locked" is large. | Home, commissary, education | Brief: body at least 20 px; low-vision users. |
| R4 | **Touch targets under 64 px.** The "Tier details" and "Mis certificados" links are text-only underlined links. The baseline tiles are about 64 px tall but their label is small. The +/- buttons are about 56 px. | Home, education, commissary | Brief: at least 64 px. |
| R5 | **Locks look like decoration.** An amber outline and a small padlock emoji; the reason is small grey text under the word "Locked". "When it unlocks" is shown only on the restriction card, not on the tile. | Home | Brief: show what, why, when, and an Appeal button, in plain language. |
| R6 | **Emoji padlock used as an icon.** It is inconsistent across platforms and is not themed. | Home, education | Replace with the self-hosted icon set, always paired with a label. |
| R7 | **Colour does too much.** Green outline = open, amber outline = locked, with only a small text change. The amber Appeal button on dark has lower emphasis than the blue Request staff bar. | Home | Status needs icon plus text, and Appeal needs to read as a first-class action. |
| R8 | **Progress is weak.** A plain bar and "75 points to Tier 4". There is no ladder of all 10 tiers and no "what Tier 4 unlocks". | Home, tier | Brief: motivating progress. |
| R9 | **Tier screen copy contradicts itself.** It says "You are at the highest tier." when the cause is a repeat-return ceiling (Tier 2 shown, earned Tier 4). This is a copy problem, not a logic one. | Tier | Confusing and could read as unfair. |
| R10 | **Fixed "Request staff" bar overlaps content.** At 1024x600 it covers about 20% of the viewport, and the last content has no bottom padding on short screens. (In the full-page screenshots it appears mid-page because the bar is fixed to the viewport.) | All | The persistent button is a baseline feature and must never hide content. |
| R11 | **Dark-only theme.** Near-black with white text, with no day or night variation. | All | Brief: calm, library-like, plus a scheduled dimmed night mode. |
| R12 | **No icons next to labels** (beyond the emoji padlock). Low-literacy users get no visual cue. | All | Brief: icons always paired with a text label. |
| R13 | **Course lists mix several states in one pattern.** Locked, prerequisite and startable courses share a card style, and the prerequisite sentence ("Termine primero: ...") is as loud as the title. | Education | Hard to scan. |
| R14 | **Spanish expands badly in the two-column tiles** ("Ajedrez contra la computadora" wraps to 3 lines and tile heights vary). | Home (es) | Layout must absorb about 30% more text. |
| R15 | **Large text just scales the one column**, so the home page reaches about 2500 px tall at 1024x600. | Home (large) | Large text needs a layout that reflows, not just a longer scroll. |
| R16 | **Untranslated content strings** in the Spanish course list ("Credit and Planning", "Trade Basics: Safety and Tools"). This comes from course content, not UI chrome. | Education (es) | Flagged for the content owner; not a UI fix. |
| R17 | **States.** There is an empty "No restrictions right now" card and a plain "Loading" text. I have not yet seen friendly error, offline or sanctioned-everything states. | All | Brief step 5. |
| R18 | **Unpaired device screen** is a single line of text on black. | Unpaired | First impression for staff and residents. |
| R19 | **No font is declared**, so the system sans renders. Metrics differ per device. | All | Self-host one legible face. |
| R20 | **Dates** read "Until Oct 25, 2026, 10:32 PM", which is long and not relative. | Locks | A relative form ("in 23 h") plus the exact time would be easier to read. |

## Staff dashboard

| # | Problem | Where | Why it matters |
|---|---|---|---|
| S1 | **Staff UI is English-only with hardcoded strings.** The brief says all text must live in i18n files. This is a larger job than a styling pass. See the open question in the review message. | All | Constraint. |
| S2 | **Navigation is 19 flat links wrapping onto two rows**, with the active page indicated by blue fill. There is no grouping. | Header | Hard to learn; the nav is the first thing seen all shift. |
| S3 | **Pending counts are not always visible.** Counts exist only as dashboard tiles. Confirmations, Appeals and Welfare in the nav have no badges. | Header | Brief: pending items always visible with counts. |
| S4 | **Tables have no sorting, filtering or sticky headers.** Roster runs 27 rows, with the header scrolling away. | Roster and others | Brief. |
| S5 | **Status uses colour pills with raw codes** ("CELL_MESS" repeated 8 times for one resident; "offline" in red). There is no icon and no plain-language label. | Roster, dashboard | Never colour alone; repeated codes should group ("CELL_MESS x8"). |
| S6 | **Weak hierarchy.** Seven or more headline numbers are the same size and weight, and the "something is wrong" ones differ only by an orange border. Recent events is a 30-row wall with identical timestamps. | Dashboard | Needs scannable priorities. |
| S7 | **Roster layout cramps cells.** The Cell and Last synced columns wrap to 2 lines; tier "2 (ceiling 2) earned 4" is grey and tiny. Pending and Appeals columns are empty. | Roster | |
| S8 | **Config editor is a raw JSON textarea** with a ~300 px window onto a long document. | Config | Fine for admins but should show structure and validation. |
| S9 | **SIMULATION banner is a pale pink strip** that scrolls away. | View as | Brief: persistent and unmistakable. |
| S10 | **Form controls use default browser styling** (grey selects, a native date input), and sizes and radii vary between pages. | View as and others | Inconsistent. |
| S11 | **Max width 1152 px on 1920 px screens** leaves wide empty margins; at 1024 px the nav and tables are tight. | All | Dense ops tool should use the width. |
| S12 | **No empty, loading or error states are styled consistently.** | All | Brief step 5. |

## Cross-cutting

- No design tokens: colours, sizes and radii are Tailwind utilities repeated in each file (`screens.tsx`, `features/*.tsx`, `staff/pages/*.tsx`).
- No shared component set beyond `resident/components.tsx` (47 lines) and `staff/ui.tsx` (120 lines).
- No accessibility checks in e2e today (axe is not installed) and no visual regression snapshots.
- No night/day theming; the kiosk is always dark.
