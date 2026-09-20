import { routes } from "@/lib/routes";

/**
 * Vendor intelligence types, palettes and column config. The vendors
 * themselves come from the backend (see `_records.ts`). All of it is synthetic:
 * the vendors, the amounts, the close history and the agent memory are
 * simulated.
 */

/* -------------------------------------------------------------------------- */
/* Palettes                                                                    */
/* -------------------------------------------------------------------------- */

export type Swatch = { bg: string; fg: string };

/** Brand marks. The comp renders vendor initials on these five tints. */
export const MARKS: readonly Swatch[] = [
  { bg: "#1D3B2A", fg: "#EAF0E6" },
  { bg: "#E9EDE7", fg: "#3E4A3C" },
  { bg: "#EDEAE3", fg: "#5A5040" },
  { bg: "#E6EBF0", fg: "#3A5465" },
  { bg: "#EDEBF2", fg: "#4A4660" },
];

export type MarkIndex = 0 | 1 | 2 | 3 | 4;

export type WorkflowName = string;

const WORKFLOW_TONES: Record<string, Swatch> = {
  "Subscription accrual": { bg: "#E9F0E5", fg: "#3C5840" },
  "Usage accrual": { bg: "#E7EDF2", fg: "#3A5465" },
  "Equipment purchase": { bg: "#E7EDF2", fg: "#3A5465" },
  "Prepaid amortization": { bg: "#EDEBF2", fg: "#4A4660" },
  "Campaign delivery": { bg: "#F2EDE4", fg: "#5E5140" },
};

/** The pill colours for a workflow; anything unlisted reads as a plain tag. */
export function workflowTone(name: WorkflowName): Swatch {
  return WORKFLOW_TONES[name] ?? { bg: "#EDEBF2", fg: "#4A4660" };
}

export type VendorState = "Autonomous" | "Waiting for evidence" | "Verified";

export const STATE_TONES: Record<VendorState, { dot: string; pulse: boolean }> = {
  Autonomous: { dot: "#63A644", pulse: true },
  "Waiting for evidence": { dot: "#D6A43C", pulse: false },
  Verified: { dot: "#2E8047", pulse: false },
};

export type AgentName =
  | "Evidence agent"
  | "Obligation agent"
  | "Estimation agent"
  | "Verification agent";

/** The comp links each agent row at its screen; these are the app-router paths. */
export const AGENT_HREFS: Record<AgentName, string> = {
  "Evidence agent": routes.evidence,
  "Obligation agent": routes.obligation,
  "Estimation agent": routes.estimation,
  "Verification agent": routes.verification,
};

/* -------------------------------------------------------------------------- */
/* Vendor records                                                              */
/* -------------------------------------------------------------------------- */

export type HistoryTag = "Verified" | "In review";
export type Confidence = "High" | "Medium";

export type CloseHistoryEntry = {
  period: string;
  amount: string;
  tag: HistoryTag;
};

export type RelationshipEntry = { when: string; what: string };
export type AgentUse = { agent: AgentName; uses: string };

export type Vendor = {
  name: string;
  id: string;
  /** The obligation this vendor's December close runs on, when one is open. */
  obligationId: string | null;
  mark: MarkIndex;
  initials: string;
  profile: string;
  treatment: string;
  workflow: WorkflowName;
  amount: string;
  /** The Decimal string behind `amount`, for sorting; null before an estimate. */
  sort: string | null;
  state: VendorState;
  category: string;
  accTreatment: string;
  confidence: Confidence;
  history: CloseHistoryEntry[];
  sources: string[];
  memory: string;
  relationship: RelationshipEntry[];
  agents: AgentUse[];
};

/* -------------------------------------------------------------------------- */
/* Table + filter configuration                                                */
/* -------------------------------------------------------------------------- */

export const ALL_STATES = "All states" as const;

export type FilterValue = typeof ALL_STATES | VendorState;

export const FILTERS: FilterValue[] = [
  ALL_STATES,
  "Autonomous",
  "Waiting for evidence",
  "Verified",
];

export type SortKey = "name" | "profile" | "workflow" | "sort" | "state";
export type SortDir = "asc" | "desc";

export const COLUMNS: { key: SortKey; label: string }[] = [
  { key: "name", label: "VENDOR" },
  { key: "profile", label: "PROFILE" },
  { key: "workflow", label: "CURRENT WORKFLOW" },
  { key: "sort", label: "AMOUNT" },
  { key: "state", label: "AGENT STATE" },
];
