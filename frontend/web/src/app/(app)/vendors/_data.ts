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

export type WorkflowName =
  | "December accrual"
  | "December usage accrual"
  | "Asset recognition"
  | "Prepaid amortization"
  | "Campaign spend"
  | "Infrastructure spend";

export const WORKFLOW_TONES: Record<WorkflowName, Swatch> = {
  "December accrual": { bg: "#E9F0E5", fg: "#3C5840" },
  "December usage accrual": { bg: "#E7EDF2", fg: "#3A5465" },
  "Asset recognition": { bg: "#E7EDF2", fg: "#3A5465" },
  "Prepaid amortization": { bg: "#EDEBF2", fg: "#4A4660" },
  "Campaign spend": { bg: "#F2EDE4", fg: "#5E5140" },
  "Infrastructure spend": { bg: "#F2EDE4", fg: "#5E5140" },
};

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

export const VENDORS: Vendor[] = [
  {
    name: "Mintlify",
    id: "VND-0412",
    mark: 0,
    initials: "M",
    profile: "Software subscription",
    treatment: "Recurring fixed",
    workflow: "December accrual",
    amount: "$1,400",
    sort: 1400,
    state: "Autonomous",
    category: "Recurring software subscription",
    accTreatment: "Monthly accrual",
    confidence: "High",
    history: [
      { period: "December 2026", amount: "$1,400", tag: "Verified" },
      { period: "November 2026", amount: "$1,200", tag: "Verified" },
      { period: "October 2026", amount: "$1,200", tag: "Verified" },
    ],
    sources: ["Contract", "Invoices", "Pricing amendment", "Usage records"],
    memory:
      "Contract price updated effective December 1, 2026. Future accruals should reference the updated subscription amount.",
    relationship: [
      { when: "Jan 2026", what: "Vendor added" },
      { when: "Oct 2026", what: "Recurring accrual established" },
      { when: "Dec 2026", what: "Contract amendment detected" },
      { when: "Future closes", what: "Use updated pricing basis" },
    ],
    agents: [
      { agent: "Evidence agent", uses: "Contract source" },
      { agent: "Obligation agent", uses: "Pricing terms" },
      { agent: "Estimation agent", uses: "Historical amount" },
      { agent: "Verification agent", uses: "Prior close comparison" },
    ],
  },
  {
    name: "OpenAI",
    id: "VND-0192",
    mark: 1,
    initials: "OA",
    profile: "API infrastructure",
    treatment: "Recurring variable",
    workflow: "December usage accrual",
    amount: "$18,600",
    sort: 18600,
    state: "Waiting for evidence",
    category: "Usage-based infrastructure",
    accTreatment: "Variable accrual",
    confidence: "Medium",
    history: [
      { period: "December 2026", amount: "$18,600", tag: "In review" },
      { period: "November 2026", amount: "$16,900", tag: "Verified" },
      { period: "October 2026", amount: "$15,400", tag: "Verified" },
    ],
    sources: ["Usage records", "Invoices", "Rate card", "Order form"],
    memory:
      "Usage varies month to month. Estimation should wait for the metered usage export before finalizing the accrual.",
    relationship: [
      { when: "Mar 2026", what: "Vendor added" },
      { when: "Jun 2026", what: "Usage-based accrual established" },
      { when: "Dec 2026", what: "Awaiting usage export" },
      { when: "Future closes", what: "Confirm metered totals" },
    ],
    agents: [
      { agent: "Evidence agent", uses: "Usage export" },
      { agent: "Obligation agent", uses: "Rate card" },
      { agent: "Estimation agent", uses: "Trailing average" },
      { agent: "Verification agent", uses: "Variance check" },
    ],
  },
  {
    name: "ASUS",
    id: "VND-8831",
    mark: 2,
    initials: "AS",
    profile: "Engineering hardware",
    treatment: "Fixed asset",
    workflow: "Asset recognition",
    amount: "$32,000",
    sort: 32000,
    state: "Verified",
    category: "Capitalized hardware",
    accTreatment: "Asset capitalization",
    confidence: "High",
    history: [
      { period: "December 2026", amount: "$32,000", tag: "Verified" },
      { period: "August 2026", amount: "$11,500", tag: "Verified" },
      { period: "April 2026", amount: "$8,200", tag: "Verified" },
    ],
    sources: ["Purchase order", "Invoices", "Asset register", "Delivery receipt"],
    memory:
      "Hardware over $5,000 is capitalized and depreciated over 36 months. Confirm receipt date before recognition.",
    relationship: [
      { when: "Feb 2026", what: "Vendor added" },
      { when: "Apr 2026", what: "Capitalization policy applied" },
      { when: "Dec 2026", what: "Equipment purchase recognized" },
      { when: "Future closes", what: "Track depreciation schedule" },
    ],
    agents: [
      { agent: "Evidence agent", uses: "Purchase order" },
      { agent: "Obligation agent", uses: "Delivery terms" },
      { agent: "Estimation agent", uses: "Capitalized value" },
      { agent: "Verification agent", uses: "Asset register match" },
    ],
  },
  {
    name: "Notability",
    id: "VND-5512",
    mark: 4,
    initials: "NO",
    profile: "Team software subscription",
    treatment: "Prepaid expense",
    workflow: "Prepaid amortization",
    amount: "$1,800/month",
    sort: 1800,
    state: "Autonomous",
    category: "Prepaid software subscription",
    accTreatment: "Straight-line amortization",
    confidence: "High",
    history: [
      { period: "December 2026", amount: "$1,800", tag: "Verified" },
      { period: "November 2026", amount: "$1,800", tag: "Verified" },
      { period: "October 2026", amount: "$1,800", tag: "Verified" },
    ],
    sources: ["Contract", "Invoices", "Amortization schedule", "Renewal notice"],
    memory:
      "Annual prepayment amortized straight-line across 12 months. No proration expected mid-term.",
    relationship: [
      { when: "May 2026", what: "Vendor added" },
      { when: "May 2026", what: "Annual prepayment recorded" },
      { when: "Dec 2026", what: "Amortization on schedule" },
      { when: "Future closes", what: "Renew or release balance" },
    ],
    agents: [
      { agent: "Evidence agent", uses: "Prepayment invoice" },
      { agent: "Obligation agent", uses: "Coverage window" },
      { agent: "Estimation agent", uses: "Monthly amortization" },
      { agent: "Verification agent", uses: "Balance rollforward" },
    ],
  },
  {
    name: "Meta",
    id: "VND-2748",
    mark: 3,
    initials: "ME",
    profile: "Advertising platform",
    treatment: "Accounts payable",
    workflow: "Campaign spend",
    amount: "$12,800",
    sort: 12800,
    state: "Autonomous",
    category: "Marketing and advertising",
    accTreatment: "Expense as incurred",
    confidence: "High",
    history: [
      { period: "December 2026", amount: "$12,800", tag: "In review" },
      { period: "November 2026", amount: "$14,200", tag: "Verified" },
      { period: "October 2026", amount: "$9,600", tag: "Verified" },
    ],
    sources: ["Platform statement", "Invoices", "Campaign report", "Spend export"],
    memory:
      "Campaign spend is billed in arrears. Accrue the platform statement total when the invoice lands after cutoff.",
    relationship: [
      { when: "Jan 2026", what: "Vendor added" },
      { when: "Feb 2026", what: "Monthly spend accrual established" },
      { when: "Dec 2026", what: "Campaign spend detected" },
      { when: "Future closes", what: "Match to platform statement" },
    ],
    agents: [
      { agent: "Evidence agent", uses: "Platform statement" },
      { agent: "Obligation agent", uses: "Billing terms" },
      { agent: "Estimation agent", uses: "Period spend" },
      { agent: "Verification agent", uses: "Invoice reconciliation" },
    ],
  },
  {
    name: "AWS",
    id: "VND-3004",
    mark: 2,
    initials: "AW",
    profile: "Cloud infrastructure",
    treatment: "Accounts payable",
    workflow: "Infrastructure spend",
    amount: "$25,300",
    sort: 25300,
    state: "Verified",
    category: "Cloud infrastructure",
    accTreatment: "Usage accrual",
    confidence: "High",
    history: [
      { period: "December 2026", amount: "$25,300", tag: "Verified" },
      { period: "November 2026", amount: "$24,100", tag: "Verified" },
      { period: "October 2026", amount: "$22,800", tag: "Verified" },
    ],
    sources: ["Billing export", "Invoices", "Savings plan", "Usage records"],
    memory:
      "Committed-use discounts apply. Use the billing export net of credits rather than the list-rate usage total.",
    relationship: [
      { when: "Jan 2026", what: "Vendor added" },
      { when: "Mar 2026", what: "Savings plan applied" },
      { when: "Dec 2026", what: "Spend within committed range" },
      { when: "Future closes", what: "Apply net-of-credit basis" },
    ],
    agents: [
      { agent: "Evidence agent", uses: "Billing export" },
      { agent: "Obligation agent", uses: "Committed use" },
      { agent: "Estimation agent", uses: "Net spend" },
      { agent: "Verification agent", uses: "Credit reconciliation" },
    ],
  },
];

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

/** The four headline numerals above the table. Static in the comp. */
export const VENDOR_KPIS: { value: string; label: string }[] = [
  { value: "24", label: "vendors" },
  { value: "18", label: "autonomous workflows" },
  { value: "6", label: "requiring review" },
  { value: "94%", label: "evidence coverage" },
];

/** The default selection the comp boots with. */
export const DEFAULT_VENDOR_ID = "VND-0412";
