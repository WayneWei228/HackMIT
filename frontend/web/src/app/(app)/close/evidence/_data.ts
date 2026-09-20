/**
 * Evidence screen dataset.
 *
 * Every constant here is lifted verbatim from the comp's script block
 * (`TrueUp Evidence.dc.html`): the document set, the zoom ladder, the scripted
 * step sequence and its delays, the status line per step, and the facts the run
 * reveals. All of it is synthetic - every upstream system is simulated.
 */

/* -------------------------------------------------------------------------- */
/* Case                                                                        */
/* -------------------------------------------------------------------------- */

export const CASE = {
  vendor: "Mintlify",
  title: "December accrual",
  meta: ["Recurring fixed", "Vendor VND-0412", "GL 6042 - Subscriptions"],
  previousAccrual: "$1,200",
  supported: "$1,400",
  difference: "+$200",
  status: "Running",
} as const;

/* -------------------------------------------------------------------------- */
/* Documents                                                                   */
/* -------------------------------------------------------------------------- */

export type DocId = "agreement" | "ap" | "prior";

export type DocTab = {
  id: DocId;
  label: string;
  /** The grey suffix in the tab strip. */
  meta: string;
  /** Page count the pager clamps to - `maxPageFor` in the comp. */
  pages: number;
  /** Page the tab opens on. */
  openAt: number;
};

export const DOC_TABS: readonly DocTab[] = [
  { id: "agreement", label: "Mintlify agreement", meta: "PDF · 14 pages", pages: 14, openAt: 6 },
  { id: "ap", label: "AP history", meta: "XLSX · 432 rows", pages: 9, openAt: 1 },
  { id: "prior", label: "Prior close", meta: "PDF · 28 pages", pages: 28, openAt: 1 },
];

/** The agreement page the pricing clause lives on - "Jump to match" lands here. */
export const MATCH_DOC: DocId = "agreement";
export const MATCH_PAGE = 6;

export const ZOOMS = ["100%", "125%", "75%"] as const;
export type Zoom = (typeof ZOOMS)[number];

export const ZOOM_SCALES: Record<Zoom, number> = {
  "100%": 1,
  "125%": 1.25,
  "75%": 0.75,
};

/* -------------------------------------------------------------------------- */
/* Scripted run                                                                */
/* -------------------------------------------------------------------------- */

/** step -> [completed checklist items, active checklist index]. */
export const SEQ: readonly (readonly [done: number, active: number])[] = [
  [0, -1],
  [1, -1],
  [2, -1],
  [2, 2],
  [2, 2],
  [3, 3],
  [3, 3],
  [4, 4],
  [5, -1],
];

/** Milliseconds between step N and step N+1. */
export const DELAYS: readonly number[] = [500, 700, 700, 800, 900, 700, 700, 900];

/** Delay between the run finishing and the auto-advance handoff. */
export const HANDOFF_DELAY = 1600;

export const STATUS: readonly string[] = [
  "Extracting supporting evidence...",
  "Extracting supporting evidence...",
  "Matching vendor record...",
  "Reading pricing terms...",
  "Reading pricing terms...",
  "Extracting effective rate...",
  "Extracting effective date...",
  "Building fact set...",
  "Evidence complete · 3 facts extracted",
];

/** The last step in the sequence - the finished state. */
export const FINAL_STEP = SEQ.length - 1;

/** Step at which the clause highlight sweeps in and the match flag appears. */
export const MATCH_STEP = 4;

/** Step at which the supported / difference figures resolve. */
export const TOTALS_STEP = 7;

export const CHECKLIST: readonly string[] = [
  "Contract selected",
  "Vendor matched",
  "Reading pricing terms",
  "Extract effective rate",
  "Build fact set",
];

export type Fact = {
  label: string;
  value: string;
  /** Step at which this fact lands. */
  at: number;
};

export const FACTS: readonly Fact[] = [
  { label: "Effective rate", value: "$1,400 / mo", at: 5 },
  { label: "Effective date", value: "Dec 1, 2026", at: 6 },
  { label: "Citation", value: "§4.2 · p. 6", at: 7 },
];

/** Seconds on the clock when the screen mounts. */
export const START_SECONDS = 42;

/* -------------------------------------------------------------------------- */
/* Document bodies                                                             */
/* -------------------------------------------------------------------------- */

export type Clause = { n: string; text: string };

export const AGREEMENT_HEADER = {
  wordmark: "mintlify",
  title: "Master Subscription Agreement",
  executed: "EXECUTED OCT 14, 2026",
} as const;

export const PAGE_5 = {
  number: "3.",
  heading: "Services",
  clauses: [
    {
      n: "3.1",
      text: "Provider shall make the Standard Workspace plan available to Customer on a subscription basis for the duration of the Term.",
    },
    {
      n: "3.2",
      text: "Customer may add Authorized Users at any time; additional seats are billed at the then-current list rate and pro-rated to the next invoice date.",
    },
    {
      n: "3.3",
      text: "Provider will use commercially reasonable efforts to maintain 99.9% monthly availability, excluding scheduled maintenance.",
    },
  ] as readonly Clause[],
} as const;

export const PAGE_6 = {
  number: "4.",
  heading: "Fees and Payment",
  lead: [
    {
      n: "4.1",
      text: "Customer shall pay the subscription fees set out in the applicable Order Form. Fees are billed monthly in arrears and are due within thirty (30) days of the invoice date.",
    },
  ] as readonly Clause[],
  /** 4.2 is rendered bespoke - it carries the highlight sweep and the match flag. */
  match: {
    n: "4.2",
    before: "Commencing December 1, 2026, the monthly subscription fee for the Standard Workspace plan shall increase from ",
    emphasis: "$1,200 to $1,400",
    after: " per month for the remainder of the Term.",
    flagLabel: "MATCH FOUND",
    flagCitation: "§4.2",
  },
  tail: [
    {
      n: "4.3",
      text: "Fees are exclusive of taxes. Customer is responsible for all applicable sales, use and withholding taxes arising from the Services.",
    },
    {
      n: "4.4",
      text: "Either party may terminate for convenience on sixty (60) days written notice prior to the end of the then-current Term.",
    },
  ] as readonly Clause[],
} as const;

export const PAGE_7 = {
  number: "5.",
  heading: "Term and Termination",
  clauses: [
    {
      n: "5.1",
      text: "The initial Term begins on the Order Form effective date and continues for twelve (12) months unless terminated in accordance with this Section.",
    },
    {
      n: "5.2",
      text: "The Term renews automatically for successive twelve (12) month periods at the then-current rate set out in Section 4.2.",
    },
    {
      n: "5.3",
      text: "Fees accrued prior to the effective date of termination remain payable in full.",
    },
  ] as readonly Clause[],
} as const;

export type ApRow = {
  date: string;
  description: string;
  amount: string;
  status: string;
};

export const AP_DOC = {
  title: "Accounts Payable — Vendor History",
  vendor: "VND-0412",
  columns: ["DATE", "DESCRIPTION", "AMOUNT", "STATUS"] as const,
  note: "12 consecutive months at $1,200 — no rate change recorded in AP",
} as const;

export const AP_ROWS: readonly ApRow[] = [
  { date: "12/01/2026", description: "Mintlify subscription", amount: "$1,200", status: "Paid" },
  { date: "11/01/2026", description: "Mintlify subscription", amount: "$1,200", status: "Paid" },
  { date: "10/01/2026", description: "Mintlify subscription", amount: "$1,200", status: "Paid" },
  { date: "09/01/2026", description: "Mintlify subscription", amount: "$1,200", status: "Paid" },
  { date: "08/01/2026", description: "Mintlify subscription", amount: "$1,200", status: "Paid" },
];

export const PRIOR_DOC = {
  eyebrow: "CLOSE MEMO · NOVEMBER 2026",
  title: "Mintlify subscription accrual",
  fields: [
    { label: "To", value: "Controller" },
    { label: "From", value: "Finance Operations" },
    { label: "Date", value: "Dec 3, 2026" },
  ],
  paragraphs: [
    "Mintlify was accrued at $1,200 for November 2026 on the basis of the prior Order Form. The vendor notified Finance of a rate change effective December 1, 2026; the amended agreement was countersigned on October 14, 2026 and supersedes the prior schedule.",
    "No adjustment was required in the November close. December should reflect the revised monthly rate for the remainder of the Term.",
  ],
} as const;

/* -------------------------------------------------------------------------- */
/* Execution rail                                                              */
/* -------------------------------------------------------------------------- */

export const RAIL = {
  eyebrow: "LIVE EXECUTION",
  running: "Running",
  factsLabel: "EXTRACTED FACTS",
  handoffLabel: "NEXT HANDOFF",
  handoffFrom: "Evidence",
  handoffTo: "Obligation",
  handoffNote: "Prepare structured evidence for the obligation agent.",
  ctaIdle: "Hand off to Obligation",
  ctaAuto: "Opening Obligation...",
} as const;

export const SOURCES_LABEL = "3 sources";
export const AGENT_LABEL = "Evidence agent";
