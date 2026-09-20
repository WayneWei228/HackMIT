import { routes } from "@/lib/routes";

/**
 * The vendor intelligence dataset, lifted verbatim from the comp script of
 * `TrueUp Vendors.dc.html`. All of it is synthetic: the vendors, the amounts,
 * the close history and the agent memory are simulated fixtures.
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

/**
 * The close workflow a vendor is in this month.
 *
 * Not a union: the backend derives the label from the period it is serving,
 * so a fixed list of names would be wrong in eleven months out of twelve.
 */
export type WorkflowName = string;

/**
 * Pill colours, keyed by what the workflow is *about* rather than by its
 * label. The month moves; "accrual", "asset", "campaign" do not.
 */
const WORKFLOW_KINDS: readonly { match: RegExp; swatch: Swatch }[] = [
  { match: /usage|metered/i, swatch: { bg: "#E7EDF2", fg: "#3A5465" } },
  { match: /accrual/i, swatch: { bg: "#E9F0E5", fg: "#3C5840" } },
  { match: /asset|equipment|capitali/i, swatch: { bg: "#E7EDF2", fg: "#3A5465" } },
  { match: /prepaid|amorti/i, swatch: { bg: "#EDEBF2", fg: "#4A4660" } },
  { match: /campaign|spend|infrastructure/i, swatch: { bg: "#F2EDE4", fg: "#5E5140" } },
];

const WORKFLOW_NEUTRAL: Swatch = { bg: "#EFEFEA", fg: "#4A4E46" };

/** The swatch for a workflow label, whatever the backend chose to call it. */
export function workflowTone(workflow: string): Swatch {
  for (const { match, swatch } of WORKFLOW_KINDS) {
    if (match.test(workflow)) return swatch;
  }
  return WORKFLOW_NEUTRAL;
}

export type VendorState = "Autonomous" | "Waiting for evidence" | "Verified";

export const STATE_TONES: Record<VendorState, { dot: string; pulse: boolean }> = {
  Autonomous: { dot: "#63A644", pulse: true },
  "Waiting for evidence": { dot: "#D6A43C", pulse: false },
  Verified: { dot: "#2E8047", pulse: false },
};

/** The backend's seven agents, in the order the close chain runs them. */
export type AgentName =
  | "Evidence agent"
  | "Detection agent"
  | "Invoice Lookup agent"
  | "Classification agent"
  | "Estimation agent"
  | "Outreach agent"
  | "Settlement agent";

/** The comp links each agent row at its screen; these are the app-router paths. */
export const AGENT_HREFS: Record<AgentName, string> = {
  "Evidence agent": routes.evidence,
  "Detection agent": routes.detection,
  "Invoice Lookup agent": routes.invoiceLookup,
  "Classification agent": routes.classification,
  "Estimation agent": routes.estimation,
  "Outreach agent": routes.outreach,
  "Settlement agent": routes.settlement,
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
  mark: MarkIndex;
  initials: string;
  profile: string;
  treatment: string;
  workflow: WorkflowName;
  amount: string;
  /** Numeric basis for the amount column sort. */
  sort: number;
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


/* -------------------------------------------------------------------------- */
/* What the close API may replace                                              */
/* -------------------------------------------------------------------------- */

/**
 * `GET /api/vendors` answers with a subset of these keys, each carrying
 * exactly the type declared above. Anything it omits keeps the value below.
 */
export type Kpi = { value: string; label: string };

/** The key set of `GET /api/vendors`. */
export type VendorsData = { VENDORS: Vendor[] };

/** The shape of a screen with no answer in it. */
export const EMPTY: VendorsData = { VENDORS: [] };

/** Nothing worth drawing a screen for. */
export function vendorsIsEmpty(data: VendorsData): boolean {
  return data.VENDORS.length === 0;
}

/**
 * The headline numerals, counted from the vendors actually loaded.
 *
 * `GET /api/vendors` serves `VENDORS` and nothing else, so the headline
 * figures are counted from that list. A figure that cannot be counted from
 * it - the comps' "evidence coverage" percentage - is not shown rather than
 * guessed.
 */
export function deriveKpis(
  vendors: readonly Vendor[],
): Kpi[] {
  const count = (state: VendorState) =>
    vendors.filter((vendor) => vendor.state === state).length;
  const autonomous = count("Autonomous");
  const waiting = count("Waiting for evidence");
  const verified = count("Verified");
  return [
    { value: String(vendors.length), label: vendors.length === 1 ? "vendor" : "vendors" },
    { value: String(autonomous), label: "autonomous workflows" },
    { value: String(waiting), label: "requiring evidence" },
    { value: String(verified), label: "verified this period" },
  ];
}
