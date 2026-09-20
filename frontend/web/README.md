# TrueUp web

The TrueUp desktop product, ported from the Maximor design comps in
`../htmlfrontend/Maximor desktop app design(2)/` to a real application stack.

All data shown is synthetic and every upstream system is simulated.

## Stack

- **Next.js 16** (App Router, Turbopack) on React 19
- **Tailwind CSS v4** - design tokens live in `src/app/globals.css` under
  `@theme`; there is no `tailwind.config.js`
- **Motion v13** (the Framer Motion successor) imported from `motion/react`
- TypeScript, ESLint

## Running it

```bash
npm install
npm run dev     # http://localhost:3000
npm run build
npm run lint
```

## Screens

| Route | Agent |
| --- | --- |
| `/cases` | All cases - case management list |
| `/vendors` | Vendor intelligence, with detail rail |
| `/close` | Evidence agent, intake view - the documents read this month |
| `/close/evidence` | Evidence agent, reader - document viewer and extracted facts |
| `/close/detection` | Detection agent - which PO lines are owed for the period |
| `/close/invoice-lookup` | Invoice Lookup agent - is it already invoiced? |
| `/close/classification` | Classification agent - recurring/one-time, fixed/variable |
| `/close/estimation` | Estimation agent - the accrual amount |
| `/close/outreach` | Outreach agent - tickets, deadlines, fallbacks |
| `/close/settlement` | Settlement agent - true-up against what actually arrived |

The seven agent screens mirror the backend's chain and hand off in that order.
In the comps each screen auto-navigated to the next on a timer; here that
handoff sits behind an `autoAdvance` prop defaulting to `false` so the app
stays navigable, and the visible affordance does the navigation.

Three of the screens share one comp and three another: Detection, Invoice
Lookup and Classification all render `close/_analysis`, and Outreach and
Settlement render `close/_controls`. What makes each of them that agent is its
route folder's `_data.ts`.

## Live data

Every screen ships with a synthetic dataset in its route folder (`_data.ts`)
and runs on it by default. Point it at the close API and the same screens fill
with real case data instead.

```bash
# 1. start the API (from the repo root)
cd startup && ../.venv/bin/python -m uvicorn close.api:app --port 8000

# 2. point the web app at it
cd frontend/web
cp .env.example .env.local        # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev

# 3. open http://localhost:3000/cases and click a case
```

`NEXT_PUBLIC_API_URL` defaults to `http://localhost:8000`, so `.env.local` is
only needed when the API lives somewhere else.

**How it works.** Each endpoint returns a JSON object whose keys are the
exported *data* constant names of the matching `_data.ts`, carrying that
constant's type. `useLiveData` (`src/lib/use-live-data.ts`) starts on the mock,
fetches once, and merges `{ ...mock, ...api }` over it - restricted to keys the
mock already declares, ignoring unknown keys and null values. Anything the API
omits keeps its synthetic value, and a failed or absent API leaves the screen
on the mock without an error. Timings, step thresholds and agent narration are
never served: they are the scripted run, not data.

| Endpoint | Fills |
| --- | --- |
| `GET /api/cases` | `{ CASES }` - each `href` is `/close?case=<period>/<case_key>` |
| `GET /api/vendors` | `{ VENDORS, VENDOR_KPIS }` |
| `GET /api/cases/{period}/{case_key}/screens/{screen}` | one screen's constants |
| `GET /api/health` | liveness |

`{screen}` is one of `ingestion`, `evidence`, `detection`, `invoice-lookup`,
`classification`, `estimation`, `outreach`, `settlement`.

The five close screens read the case from `?case=<period>/<case_key>` and every
link between them carries it (`withCase` in `src/lib/routes.ts`). With no
`case` param a close screen is a demo and makes no request at all. A small
"Live data" / "Demo data" pill in each screen's header says which it is, with
the case id beside it.

## Layout

```
src/
  app/
    (app)/            route group - every screen, wrapped in the desktop shell
      layout.tsx
      cases/ vendors/ close/{,evidence,obligation,estimation,verification}/
        page.tsx      the route
        _components/  pieces of that screen
        _data.ts      that screen's synthetic dataset
    globals.css       design tokens (@theme) and base styles
    layout.tsx        fonts and document shell
  components/
    shell/            app frame and sidebar, shared by every screen
    ui/               primitives and the icon set
  lib/
    cn.ts motion.ts routes.ts
```

`CONVENTIONS.md` holds the porting contract: fidelity rules, the comp dialect,
and the motion policy.

## Design system

The palette is a warm paper neutral ramp with a single TrueUp green accent.
Display numerals and page titles are Newsreader; the rest is the Helvetica
stack the comps specified. Token values were lifted from the comps unchanged -
the greys deliberately differ by only a few hex points and should not be
rounded to a tidier scale.

Motion is deliberately quiet: one easing, three durations, 4-10px of travel.
It exists to explain causality in an agent run - a fact arrived, a step
finished - not to decorate. `prefers-reduced-motion` skips scripted timelines
and renders the finished state.

## Where the port deliberately departs from the comps

Every departure below is a decision, not an oversight.
Everything else was matched to the comps' measured geometry.

**Auto-advance is off by default.**
The comps navigate to the next agent screen on a timer at the end of their scripted run.
That makes the app impossible to browse, so the handoff now sits behind an `autoAdvance` prop defaulting to `false`, and the visible CTA does the navigation.

**The active sidebar leaf uses one treatment.**
The comps disagree with each other: five of the six that mark a leaf use the `#E9EFE8` wash alone at a 42px indent, while `TrueUp All Cases` adds a 6px green bullet and pulls its label to a 23px indent.
The shared sidebar follows the majority, which is also the treatment that keeps every leaf label on the same baseline when the active row changes.

**Serif numerals are not tabular.**
None of the comps' 140 Newsreader runs set `font-variant-numeric`, so neither do ours.

**The `•••` glyph renders in the app font.**
The comps' `•••` buttons declare no `font-family`, so the browser falls back to its `<button>` default of Arial.
That is the absence of a decision rather than one, so the port lets the glyph inherit the app's Helvetica stack.
The button box, colour, letter-spacing and optical centre are identical either way.

## How the port was verified

Each route was rendered beside its comp at 1536x1024 in Chrome and compared by measured geometry, not by eye alone: for every text run the two pages share, the port's `top`, `left`, `font-size`, `weight`, `letter-spacing`, `colour` and family were diffed against the comp's.
Because the agent screens run scripted timelines, a difference counts only if it persists across two independent samples - anything that moves between samples is the timeline, not the layout.
On that measure `/cases`, `/vendors`, `/close` and `/close/obligation` report zero positional and zero typographic differences, and the shared sidebar matches the comp's row positions exactly.
