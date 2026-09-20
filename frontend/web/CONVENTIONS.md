# TrueUp web - conversion conventions

This app is a faithful port of the Maximor desktop design comps at
`../htmlfrontend/Maximor desktop app design(2)/*.dc.html` to Next.js 16 (App
Router) + React 19 + Tailwind v4 + Motion.

All data is synthetic and every upstream system is simulated.

## Stack facts

- Tailwind **v4**: tokens live in `src/app/globals.css` under `@theme`. There is
  no `tailwind.config.js`. Add a token there rather than reaching for a raw hex
  twice.
- Animation library is **`motion`** (the Framer Motion successor). Import from
  `motion/react`: `import { motion, AnimatePresence } from "motion/react"`.
  Never import from `framer-motion`.
- Every file that uses hooks, `motion`, or event handlers needs `"use client"`.

## Fidelity rules

The comps are the spec. Match them to the pixel.

1. **Reproduce exact values.** The comps use `13.5px`, `10.5px`, `7px` radii,
   and greys that differ by two or three hex points. Do not round them to the
   nearest Tailwind step. Named tokens exist for every recurring value - check
   `globals.css` first, use an arbitrary value (`text-[27px]`, `bg-[#F3F3EE]`)
   only for genuine one-offs.
2. **Keep the layout mechanics.** The comps are desktop-first: the shell scrolls
   horizontally and `main` carries a `min-width`. Keep those. Do not add
   responsive breakpoints that were not in the comp.
3. **Typography.** Display numerals and page titles are Newsreader, applied with
   the `font-display` utility. Everything else inherits the Helvetica stack from
   `body`. Give a sans numeral run `tabular-nums` only where the comp sets
   `font-variant-numeric`; no Newsreader run in any comp sets it, so never pair
   `tabular-nums` with `font-display`.
4. **Copy is verbatim.** Vendor names, amounts, timestamps, status strings, and
   agent narration all come across word for word.

## Route layout

Pages live in the `(app)` route group: `src/app/(app)/<segment>/page.tsx`. The
group does not appear in the URL. `src/app/(app)/layout.tsx` already wraps every
page in `AppShell`, so a page renders only its own content - do not render
`AppShell` or `Sidebar` yourself. That is usually a single `<main>`; a screen
whose comp puts a detail rail beside the content returns `<main>` and `<aside>`
as siblings in a fragment, because both are children of the shell's flex row.

## What to reuse

| Need | Import |
| --- | --- |
| App frame + sidebar | `@/components/shell/app-shell` -> `<AppShell>` |
| Icons | `@/components/ui/icons` |
| Buttons, search, tabs, stats, tags, column headers | `@/components/ui/primitives` |
| Class merging | `cn` from `@/lib/cn` |
| Shared variants and easings | `@/lib/motion` |
| Route paths | `routes`, `agentChain` from `@/lib/routes` |

`AppShell` already renders `<Sidebar/>`; a page renders only its `<main>`.
The sidebar derives its active state from `usePathname`, so pages do not pass it.

## Traps found while porting

- **A fixed-height `<button>` centres its content.** Chrome vertically centres
  the contents of a `<button>` with a set height, so a card ported from a comp's
  `<div>` floats its body down by half the leftover space. Give any such button
  `flex flex-col`. This silently cost two screens up to 46px of drift.
- **`cn` needs to know the theme's scales.** `src/lib/cn.ts` registers the
  font-size, tracking and shadow names with tailwind-merge. Without that,
  `cn("text-ui", "text-ink")` reads `text-ui` as a colour and drops it.
- **No size carries a line-height.** `globals.css` clears Tailwind's stock
  `--text-*` namespace and sets `line-height: normal` on `body`, because the
  comps set line-height nowhere. Add `leading-*` explicitly when a comp does.

## Motion policy

The comps animate on a scripted timeline: an agent run advances through steps on
fixed delays, driving checklist state, status strings, and fact cards. Keep the
timings exactly, but express them idiomatically:

- The step timeline stays a `useEffect` with `setTimeout`, cleared on unmount.
- The **visual** result of a step uses Motion: `AnimatePresence` for things that
  appear and leave, `layoutId` for anything that slides between positions,
  variants from `@/lib/motion` for lists that settle in.
- Travel stays small - 4 to 10px - and eased out. Nothing bounces, nothing
  scales up from zero, nothing slides across the screen.
- Respect `useReducedMotion()`: with it on, skip the timeline and render the
  finished state.
- Auto-advance to the next screen is **off by default** in this port. Expose it
  behind an `autoAdvance` prop that defaults to `false` so the app is navigable;
  the visible "Continue" / handoff affordance does the navigation.

## File ownership

Each screen owns its route folder and its own `_components/` directory. Do not
edit files outside your assigned folder, and do not edit shared files in
`src/components/shell`, `src/components/ui`, `src/lib`, or `globals.css` - if
something shared is missing, build it locally in your folder and say so in your
report.

## Definition of done

- `npx tsc --noEmit` is clean for your files.
- `npx eslint src/app/<your route>` is clean.
- No `any`, no unused imports, no inline `style={{}}` except for genuinely
  dynamic values (a measured width, a transform driven by state).
