/**
 * Close case dataset.
 *
 * Every string, number and delay below is lifted verbatim from the
 * `TrueUp Close Case.dc.html` comp - the template markup for the ten source
 * cards and the `data-dc-script` block that drives the ingestion timeline.
 *
 * All data is synthetic and every upstream system is simulated.
 */

/* -------------------------------------------------------------------------- */
/* Sources                                                                     */
/* -------------------------------------------------------------------------- */

export type SourceId =
  | "agreement"
  | "ap"
  | "prior"
  | "vendor"
  | "gl"
  | "invoice"
  | "po"
  | "email"
  | "slack"
  | "usage";

/** `ORDER` in the comp script - also the order the cards render in. */
export const SOURCE_ORDER: readonly SourceId[] = [
  "agreement",
  "ap",
  "prior",
  "vendor",
  "gl",
  "invoice",
  "po",
  "email",
  "slack",
  "usage",
];

/** `NAMES` in the comp script - the label shown in the rail's selected list. */
export const SOURCE_NAMES: Record<SourceId, string> = {
  agreement: "Mintlify agreement",
  ap: "AP history",
  prior: "Prior close",
  vendor: "Vendor master",
  gl: "General ledger",
  invoice: "Vendor invoice",
  po: "PO / Order form",
  email: "Email thread",
  slack: "Slack export",
  usage: "Usage report",
};

export type SourceGlyph = "page" | "mail" | "chat";

/** The card footer: glyph, file name, and the `FORMAT · detail` caption. */
export type SourceFooter = {
  id: SourceId;
  glyph: SourceGlyph;
  title: string;
  format: string;
  detail: string;
};

export const SOURCE_FOOTERS: Record<SourceId, SourceFooter> = {
  agreement: {
    id: "agreement",
    glyph: "page",
    title: "Mintlify agreement",
    format: "PDF",
    detail: "14 pages",
  },
  ap: {
    id: "ap",
    glyph: "page",
    title: "AP history",
    format: "XLSX",
    detail: "24 rows",
  },
  prior: {
    id: "prior",
    glyph: "page",
    title: "Prior close",
    format: "DOCX",
    detail: "3 pages",
  },
  vendor: {
    id: "vendor",
    glyph: "page",
    title: "Vendor master",
    format: "PDF",
    detail: "2 pages",
  },
  gl: {
    id: "gl",
    glyph: "page",
    title: "General ledger",
    format: "XLSX",
    detail: "48 rows",
  },
  invoice: {
    id: "invoice",
    glyph: "page",
    title: "Vendor invoice",
    format: "PDF",
    detail: "1 page",
  },
  po: {
    id: "po",
    glyph: "page",
    title: "PO / Order form",
    format: "PDF",
    detail: "6 pages",
  },
  email: {
    id: "email",
    glyph: "mail",
    title: "Email thread",
    format: "EML",
    detail: "12 messages",
  },
  slack: {
    id: "slack",
    glyph: "chat",
    title: "Slack export",
    format: "TXT",
    detail: "8 messages",
  },
  usage: {
    id: "usage",
    glyph: "page",
    title: "Usage report",
    format: "PDF",
    detail: "4 pages",
  },
};

/* -------------------------------------------------------------------------- */
/* Filter tabs                                                                 */
/* -------------------------------------------------------------------------- */

/** `TABS` in the comp script. Only six of the ten sources get their own tab. */
export type TabId = "all" | "agreement" | "ap" | "prior" | "vendor" | "gl";

export type TabGlyph =
  | "sources"
  | "document"
  | "spreadsheet"
  | "memo"
  | "record"
  | "ledger";

export type SourceTab = { id: TabId; label: string; glyph: TabGlyph };

export const SOURCE_TABS: readonly SourceTab[] = [
  { id: "all", label: "All sources (10)", glyph: "sources" },
  { id: "agreement", label: "Mintlify agreement (1)", glyph: "document" },
  { id: "ap", label: "AP history (1)", glyph: "spreadsheet" },
  { id: "prior", label: "Prior close (1)", glyph: "memo" },
  { id: "vendor", label: "Vendor master (1)", glyph: "record" },
  { id: "gl", label: "General ledger (1)", glyph: "ledger" },
];

/* -------------------------------------------------------------------------- */
/* Case header                                                                 */
/* -------------------------------------------------------------------------- */

export const CASE_META: readonly string[] = [
  "Recurring fixed",
  "Vendor VND-0412",
  "GL 6042 - Subscriptions",
];

export type CaseStat = { label: string; value: string; muted?: boolean };

export const CASE_STATS: readonly CaseStat[] = [
  { label: "PREVIOUS ACCRUAL", value: "$1,200" },
  { label: "SUPPORTED", value: "—", muted: true },
  { label: "DIFFERENCE", value: "—", muted: true },
];

export const CASE_STATUS_LABEL = "STATUS";
export const CASE_STATUS_VALUE = "Running";

/* -------------------------------------------------------------------------- */
/* Ingestion timeline - the `data-dc-script` constants, unchanged              */
/* -------------------------------------------------------------------------- */

/** Step index -> the source that gets selected when that step lands. */
export const SELECT_AT: Readonly<Record<number, SourceId>> = {
  3: "agreement",
  4: "ap",
  5: "prior",
};

/** Step index at which each of the five checklist tasks is done. */
export const TASK_DONE: readonly number[] = [1, 2, 6, 7, 8];

export const STEPS = 8;

export const DELAYS: readonly number[] = [
  500, 650, 600, 550, 550, 650, 700, 750,
];

/** Milliseconds from mount to the final step. */
export const TOTAL_RUN_MS = DELAYS.reduce((a, b) => a + b, 0);

/** Extra dwell before the comp hands off to the Evidence screen. */
export const HANDOFF_DELAY_MS = 1500;

export const STATUS: readonly string[] = [
  "Loading file universe...",
  "Clustering vendor-related sources...",
  "Selecting relevant files...",
  "Selecting relevant files...",
  "Selecting relevant files...",
  "Removing irrelevant sources...",
  "Preparing evidence handoff...",
  "Ingestion complete · 3 files selected",
  "Ingestion complete · handing off to Evidence",
];

export const CHECKLIST: readonly string[] = [
  "File universe loaded",
  "Vendor-related sources clustered",
  "Selecting relevant files",
  "Remove irrelevant sources",
  "Prepare evidence handoff",
];

/** The three stages that sit dormant below Ingestion and Evidence. */
export const WAITING_STAGES: readonly { index: string; label: string }[] = [
  { index: "03", label: "Obligation" },
  { index: "04", label: "Estimation" },
  { index: "05", label: "Verification" },
];

export const FILES_LOADED_LABEL = "10 files loaded";
export const AGENT_NAME = "Ingestion agent";

export const HANDOFF_FROM = "Ingestion";
export const HANDOFF_TO = "Evidence";
export const HANDOFF_BLURB =
  "Prepare selected files for evidence extraction and analysis.";
export const CTA_IDLE_LABEL = "Run evidence agent";
export const CTA_ADVANCING_LABEL = "Opening Evidence...";

/* -------------------------------------------------------------------------- */
/* Rail geometry                                                               */
/* -------------------------------------------------------------------------- */

export const RAIL_DEFAULT_WIDTH = 330;
export const RAIL_MIN_WIDTH = 288;
export const RAIL_MAX_WIDTH = 620;

/* -------------------------------------------------------------------------- */
/* Card bodies                                                                 */
/* -------------------------------------------------------------------------- */

export type LedgerRow = { date: string; description: string; amount: string };
export type FieldRow = { label: string; value: string };

/** Mintlify agreement - clause 4.2 of the Master Subscription Agreement. */
export const AGREEMENT_CLAUSE = {
  vendor: "Mintlify",
  documentName: "Master Subscription Agreement",
  section: "4. Fees and Payment",
  number: "4.2",
  body:
    "Commencing December 1, 2026, the monthly subscription fee for the Standard Workspace plan shall increase from $1,200 to $1,400 per month for the remainder of the term.",
} as const;

/** Accounts Payable vendor history. */
export const AP_ROWS: readonly LedgerRow[] = [
  { date: "10/01/2026", description: "Mintlify subscription", amount: "$1,200" },
  { date: "09/01/2026", description: "Mintlify subscription", amount: "$1,200" },
  { date: "08/01/2026", description: "Mintlify subscription", amount: "$1,200" },
  { date: "07/01/2026", description: "Mintlify subscription", amount: "$1,200" },
];

/** Prior close memo. */
export const PRIOR_CLOSE = {
  title: "December 2026",
  kicker: "Close Memo",
  fields: [
    { label: "To", value: "Controller" },
    { label: "From", value: "Finance Operations" },
    { label: "Date", value: "Dec 3, 2026" },
    { label: "Subject", value: "Mintlify subscription accrual" },
  ] as readonly FieldRow[],
  body:
    "We will accrue Mintlify at the increased $1,400 monthly rate starting December 1, 2026, per the amended agreement signed in November.",
} as const;

/** Vendor master record. The address is the only two-line value. */
export const VENDOR_FIELDS: readonly FieldRow[] = [
  { label: "Vendor ID", value: "VND-0412" },
  { label: "Legal name", value: "Mintlify, Inc." },
  { label: "Entity type", value: "Corporation" },
  { label: "Status", value: "Active" },
  { label: "Pay terms", value: "Net 30" },
];

export const VENDOR_ADDRESS = {
  label: "Address",
  lines: ["548 Market St", "San Francisco, CA 94104"],
} as const;

export const VENDOR_TAX_ID: FieldRow = { label: "Tax ID", value: "XX-XXX7890" };

/** General ledger account activity. */
export const GL_ROWS: readonly LedgerRow[] = [
  { date: "11/01/2026", description: "JE-10283", amount: "$1,200" },
  { date: "10/31/2026", description: "JE-09821", amount: "$1,200" },
  { date: "09/30/2026", description: "JE-88202", amount: "$1,200" },
  { date: "08/31/2026", description: "JE-77211", amount: "$1,200" },
];

/** Vendor invoice. */
export const INVOICE = {
  title: "Invoice INV-77631",
  kicker: "Mintlify, Inc.",
  fields: [
    { label: "Invoice #", value: "INV-77631" },
    { label: "Date", value: "12/01/2026" },
    { label: "Due date", value: "12/01/2026" },
  ] as readonly FieldRow[],
  totalLabel: "Total",
  totalValue: "$1,200",
} as const;

/** PO / order form. */
export const ORDER_FORM = {
  title: "Order Form",
  kicker: "Mintlify",
  fields: [
    { label: "Customer", value: "TrueUp, Inc." },
    { label: "Order date", value: "11/15/2024" },
    { label: "Term", value: "12 months" },
    { label: "Plan", value: "Standard Workspace" },
  ] as readonly FieldRow[],
} as const;

/** Email thread. */
export const EMAIL_THREAD = {
  subject: "Re: Mintlify renewal",
  fields: [
    { label: "From", value: "Alex Chen <alex@mintlify.com>" },
    { label: "To", value: "finance@trueup.com" },
    { label: "Date", value: "Oct 20, 2026" },
  ] as readonly FieldRow[],
  body: [
    "Hi team,",
    "Just following up on the upcoming renewal. The new pricing will be $1,400 per month starting December 1, 2026 as discussed.",
    "Best,",
    "Alex",
  ] as readonly string[],
} as const;

/** Slack export. */
export type SlackMessage = { author: string; at: string; body: string };

export const SLACK_THREAD = {
  title: "Slack – #vendor",
  kicker: "8 messages",
  messages: [
    {
      author: "Priya",
      at: "10/14",
      body: "Heads-up — Mintlify is increasing pricing to $1,400 in Dec.",
    },
    { author: "Matt", at: "10/14", body: "Shall we pull this for the accrual?" },
    {
      author: "Priya",
      at: "10/15",
      body: "Shared the updated agreement in this thread.",
    },
  ] as readonly SlackMessage[],
} as const;

/** Usage report sparkline - percentage heights, tallest bar reads darker. */
export const USAGE_BARS: readonly number[] = [
  34, 46, 30, 58, 44, 72, 62, 88, 100,
];
