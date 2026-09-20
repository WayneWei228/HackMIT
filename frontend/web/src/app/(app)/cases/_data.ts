import { routes } from "@/lib/routes";

/**
 * The case-management dataset, lifted verbatim from the comp's script block.
 * All data is synthetic and every upstream system is simulated.
 */

export type CaseCategory =
  "Accruals" | "Prepaids" | "Fixed Assets" | "Accounts Payable";

export type CaseStatus =
  "Running" | "In progress" | "Queued" | "Close-ready" | "Complete";

export type CaseStage =
  "Ingestion" | "Evidence" | "Obligation" | "Estimation" | "Verification";

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
  /** Whole dollars; the comp formats with a thousands separator at render. */
  amount: number;
  stage: CaseStage;
  status: CaseStatus;
  date: string;
  time: string;
  /** Sortable stamp, YYYYMMDD.HHMM. */
  ts: number;
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

export const CASES: readonly CaseRecord[] = [
  {
    vendor: "Mintlify",
    initials: "M",
    mark: 0,
    item: "December accrual",
    category: "Accruals",
    amount: 1400,
    stage: "Verification",
    status: "Running",
    date: "Dec 1, 2026",
    time: "10:24 AM",
    ts: 20261201.1024,
    href: routes.verification,
  },
  {
    vendor: "OpenAI",
    initials: "OA",
    mark: 1,
    item: "API usage accrual",
    category: "Accruals",
    amount: 18600,
    stage: "Evidence",
    status: "Running",
    date: "Dec 1, 2026",
    time: "9:18 AM",
    ts: 20261201.0918,
    href: routes.evidence,
  },
  {
    vendor: "ASUS",
    initials: "AS",
    mark: 2,
    item: "Equipment purchase",
    category: "Fixed Assets",
    amount: 40000,
    stage: "Obligation",
    status: "In progress",
    date: "Dec 1, 2026",
    time: "8:45 AM",
    ts: 20261201.0845,
    href: routes.obligation,
  },
  {
    vendor: "Meta",
    initials: "ME",
    mark: 3,
    item: "Campaign spend",
    category: "Accounts Payable",
    amount: 12800,
    stage: "Estimation",
    status: "Running",
    date: "Nov 30, 2026",
    time: "4:32 PM",
    ts: 20261130.1632,
    href: routes.estimation,
  },
  {
    vendor: "Notability",
    initials: "NO",
    mark: 4,
    item: "Prepaid subscription",
    category: "Prepaids",
    amount: 2400,
    stage: "Ingestion",
    status: "Queued",
    date: "Nov 30, 2026",
    time: "2:17 PM",
    ts: 20261130.1417,
    href: routes.closeCase,
  },
  {
    vendor: "Slack",
    initials: "SL",
    mark: 5,
    item: "Workspace subscription",
    category: "Prepaids",
    amount: 7200,
    stage: "Verification",
    status: "Close-ready",
    date: "Nov 30, 2026",
    time: "11:06 AM",
    ts: 20261130.1106,
    href: routes.verification,
  },
  {
    vendor: "AWS",
    initials: "AW",
    mark: 2,
    item: "Infrastructure spend",
    category: "Accounts Payable",
    amount: 25300,
    stage: "Evidence",
    status: "Complete",
    date: "Nov 29, 2026",
    time: "6:14 PM",
    ts: 20261129.1814,
    href: routes.evidence,
  },
  {
    vendor: "Deel",
    initials: "DE",
    mark: 1,
    item: "Contractor services",
    category: "Accounts Payable",
    amount: 9100,
    stage: "Estimation",
    status: "Complete",
    date: "Nov 29, 2026",
    time: "3:22 PM",
    ts: 20261129.1522,
    href: routes.estimation,
  },
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
 * Tab counts are taken from the whole dataset - they ignore the search box and
 * the status filter, so the row of tabs never reshuffles while you type.
 */
export const TAB_COUNTS: Record<CategoryTab, number> = CATEGORY_TABS.reduce(
  (acc, tab) => {
    acc[tab] = CASES.filter(
      (item) => tab === "All" || item.category === tab,
    ).length;
    return acc;
  },
  {} as Record<CategoryTab, number>,
);

const dollars = new Intl.NumberFormat("en-US");

export function formatAmount(amount: number): string {
  return `$${dollars.format(amount)}`;
}
