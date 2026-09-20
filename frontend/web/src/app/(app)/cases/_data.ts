import type { CaseStatus, FrontStage } from "@/lib/api-types";

/**
 * Case-management types, palettes and column config. The rows themselves come
 * from the backend (see `_records.ts`). All data is synthetic and every
 * upstream system is simulated.
 */

export type CaseCategory =
  "Accruals" | "Prepaids" | "Fixed Assets" | "Accounts Payable";

export type CaseStage = FrontStage;
export type { CaseStatus };

/** The columns a reader can sort the table by. */
export type SortKey =
  "vendor" | "item" | "category" | "amount" | "stage" | "status" | "ts";

export type CaseRecord = {
  vendor: string;
  initials: string;
  /** Index into MARKS - the vendor monogram's paper/ink pair. */
  mark: number;
  obligationId: string;
  item: string;
  category: CaseCategory;
  /** A Decimal string such as "1400.00", or null before an estimate exists. */
  amount: string | null;
  stage: CaseStage;
  status: CaseStatus;
  /** A Pending case the close can still start. */
  canStart: boolean;
  /** Stages the backend reports as completed; null when the backend does not say. */
  stagesCompleted: readonly FrontStage[] | null;
  /** The agent working the case, or the one that runs next. */
  currentAgent: string | null;
  /** A stage call for this case is in flight right now. */
  running: boolean;
  date: string;
  time: string;
  /** Sortable stamp: milliseconds since the epoch. */
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

export { STATUS_STYLES } from "@/lib/status-styles";

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

/** The order category tabs appear in; only the categories with cases are shown. */
export const CATEGORY_ORDER: readonly CaseCategory[] = [
  "Accruals",
  "Prepaids",
  "Fixed Assets",
  "Accounts Payable",
];

export const STATUS_OPTIONS: readonly StatusFilter[] = [
  ALL_STATUSES,
  "Pending",
  "Running",
  "In progress",
  "Needs review",
  "Waiting",
  "Blocked",
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
