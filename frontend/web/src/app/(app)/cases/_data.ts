/**
 * The case-management screen's vocabulary - and nothing else.
 *
 * The product holds no content of its own: every case, vendor, amount and
 * timestamp comes from `GET /api/cases`, which starts empty and is filled by
 * running a month. So this file carries only what the *renderer* needs to be
 * able to draw a row it has never seen: the row's type, the palettes, the
 * filter vocabularies, and one empty initial value.
 */

export type CaseCategory =
  "Accruals" | "Prepaids" | "Fixed Assets" | "Accounts Payable";

export type CaseStatus =
  "Running" | "In progress" | "Queued" | "Close-ready" | "Complete";

/** The seven agents of the close chain, in the order they run. */
export type CaseStage =
  | "Evidence"
  | "Detection"
  | "Invoice Lookup"
  | "Classification"
  | "Estimation"
  | "Outreach"
  | "Settlement";

/** The columns a reader can sort the table by. */
export type SortKey =
  "vendor" | "item" | "category" | "amount" | "stage" | "status" | "ts";

export type CaseRecord = {
  vendor: string;
  initials: string;
  /** Index into MARKS - the vendor monogram's paper/ink pair. */
  mark: number;
  item: string;
  category: CaseCategory;
  /** Whole dollars; formatted with a thousands separator at render. */
  amount: number;
  stage: CaseStage;
  status: CaseStatus;
  date: string;
  time: string;
  /** Sortable stamp, YYYYMMDD.HHMM. */
  ts: number;
  /** `"/close?case=<period>/<case_key>"`, URL-encoded, as the API emits it. */
  href: string;
};

/** Category pill colours. */
export const CATEGORY_STYLES: Record<CaseCategory, { bg: string; fg: string }> =
  {
    Accruals: { bg: "#E9F0E5", fg: "#3C5840" },
    Prepaids: { bg: "#EDEBF2", fg: "#4A4660" },
    "Fixed Assets": { bg: "#E7EDF2", fg: "#3A5465" },
    "Accounts Payable": { bg: "#F2EDE4", fg: "#5E5140" },
  };

/** Status dot colour, and whether the dot carries a live pulse ring. */
export const STATUS_STYLES: Record<
  CaseStatus,
  { dot: string; pulse: boolean }
> = {
  Running: { dot: "#63A644", pulse: true },
  "In progress": { dot: "#9AA096", pulse: false },
  Queued: { dot: "#C0C5BB", pulse: false },
  "Close-ready": { dot: "#2E8047", pulse: false },
  Complete: { dot: "#1F5132", pulse: false },
};

/** Monogram palettes, indexed by `CaseRecord.mark`. */
export const MARKS: readonly { bg: string; fg: string }[] = [
  { bg: "#1D3B2A", fg: "#EAF0E6" },
  { bg: "#E9EDE7", fg: "#3E4A3C" },
  { bg: "#EDEAE3", fg: "#5A5040" },
  { bg: "#E6EBF0", fg: "#3A5465" },
  { bg: "#EDEBF2", fg: "#4A4660" },
  { bg: "#E9F0E5", fg: "#3C5840" },
];

export type CategoryTab = "All" | CaseCategory;
export type StatusFilter = "All statuses" | CaseStatus;

export const ALL_STATUSES = "All statuses" satisfies StatusFilter;

export const CATEGORY_TABS: readonly CategoryTab[] = [
  "All",
  "Accruals",
  "Prepaids",
  "Fixed Assets",
  "Accounts Payable",
];

export const STATUS_OPTIONS: readonly StatusFilter[] = [
  ALL_STATUSES,
  "Running",
  "In progress",
  "Queued",
  "Close-ready",
  "Complete",
];

export const COLUMNS: readonly { key: SortKey; label: string }[] = [
  { key: "vendor", label: "VENDOR" },
  { key: "item", label: "CLOSE ITEM" },
  { key: "category", label: "CATEGORY" },
  { key: "amount", label: "AMOUNT" },
  { key: "stage", label: "AGENT STAGE" },
  { key: "status", label: "STATUS" },
  { key: "ts", label: "UPDATED" },
];

/**
 * Tab counts are taken from the rows the API returned - they ignore the search
 * box and the status filter, so the row of tabs never reshuffles while you
 * type. A month with no cases counts zeroes, which is the truth.
 */
export function countByCategory(
  cases: readonly CaseRecord[],
): Record<CategoryTab, number> {
  return CATEGORY_TABS.reduce(
    (acc, tab) => {
      acc[tab] = cases.filter(
        (item) => tab === "All" || item.category === tab,
      ).length;
      return acc;
    },
    {} as Record<CategoryTab, number>,
  );
}

const dollars = new Intl.NumberFormat("en-US");

export function formatAmount(amount: number): string {
  return `$${dollars.format(amount)}`;
}

/* -------------------------------------------------------------------------- */
/* What the close API answers with                                             */
/* -------------------------------------------------------------------------- */

/** `GET /api/cases[?period=YYYY-MM]` -> `{ CASES }`. */
export type CasesData = { CASES: readonly CaseRecord[] };

/** The starting point: nothing, until a month has been run. */
export const EMPTY: CasesData = { CASES: [] };
