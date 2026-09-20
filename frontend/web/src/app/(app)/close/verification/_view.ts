import type {
  AuditReport,
  CloseView,
  ControllerView,
  Escalation,
  Header,
  JournalEntry,
  ObligationDetail,
  OutreachMessage,
  Person,
  Received,
  ReconciliationView,
  Row,
  RuleRef,
  StageCheck,
} from "@/lib/api-types";
import { formatMoney } from "@/lib/money";

import type { Assertion, Control, VerificationData } from "./_data";

export type JournalLineView = { side: string; account: string; amount: string };

export type VerificationScreenView = {
  obligationId: string;
  header: Header;
  /** What the run replays: one control per policy rule, one assertion per recorded claim. */
  data: VerificationData;
  amount: string;
  /** Set when the estimate was built without the owner's reply, from part of the period's data. */
  fallbackNote: string | null;
  finalRows: Row[];
  journal: JournalLineView[];
  entries: JournalEntry[];
  controller: ControllerView;
  controllerId: string;
  people: Person[];
  reconciliation: ReconciliationView | null;
  outreach: OutreachMessage[];
  rulesApplied: RuleRef[];
  policySummary: string | null;
  available: boolean;
  /** The Auditor's re-performance of the controls on this obligation, when one exists. */
  audit: AuditReport | null;
  received: Received | null;
  stageChecks: StageCheck[] | null;
  escalation: Escalation | null;
  trailVersion: string;
};

const TAGS = { PASS: "Passed", HIT: "Flagged", NOTE: "Noted" } as const;

export function buildVerificationView(
  detail: ObligationDetail,
  close: Pick<CloseView, "controller_id" | "people">,
  audit: AuditReport | null,
): VerificationScreenView {
  const { verification, estimation, header } = detail;

  const controls: Control[] = verification.rules.map((rule, i) => ({
    index: String(i + 1).padStart(2, "0"),
    title: rule.name,
    subtitle: rule.rule_id,
    body: rule.detail,
    tone: rule.status === "PASS" ? "ok" : "warn",
    doneTag: TAGS[rule.status],
  }));

  const assertions: Assertion[] = verification.assertions.map((row) => ({
    label: row.label,
    value: /^-?\d+\.\d{2}$/.test(row.value)
      ? formatMoney(row.value)
      : row.label === "Journal impact"
        ? row.value.replace(/\d+\.\d{2}/g, (amount) => formatMoney(amount))
        : row.value,
    plain: row.label === "Journal impact" || row.label === "Basis" || row.label === "Service period",
  }));

  const duplicateRule = verification.rules.find((rule) => rule.rule_id === "POL-02");
  const credits = estimation.checks.find((check) => check.name === "credits_and_refunds");
  /* An extra check is listed only when the backend recorded the rule or check behind it. */
  const extras = [
    ...(duplicateRule
      ? [{ label: "No duplicate accrual", ok: duplicateRule.status === "PASS" }]
      : []),
    ...(credits ? [{ label: "No offsetting credits", ok: credits.result === "none found" }] : []),
  ];

  const accrual = verification.entries.find(
    (entry) => entry.entry_type === "ACCRUAL" || entry.entry_type === "PROPOSED",
  );
  const gl = estimation.expense_account ?? "-";

  return {
    obligationId: header.obligation_id,
    header,
    fallbackNote: estimation.fallback
      ? `Reply did not arrive by the deadline; estimate built from ${estimation.fallback.coverage}`
      : null,
    data: {
      controls,
      assertions,
      extras,
      scanItems: [],
      finalStatus: header.status,
      noteTitle: verification.note_title,
      noteBody: verification.note_body,
    },
    amount: formatMoney(header.supported),
    finalRows: [
      { label: "Service period", value: detail.obligation.service_period },
      { label: "GL account", value: gl },
      { label: "Vendor", value: `${header.vendor_name} (${header.vendor_id})` },
    ],
    journal: (accrual?.lines ?? []).map((line) => ({
      side: line.side,
      account: line.account,
      amount: formatMoney(line.amount),
    })),
    entries: verification.entries,
    controller: verification.controller,
    controllerId: close.controller_id,
    people: close.people,
    reconciliation: verification.reconciliation,
    outreach: verification.outreach,
    rulesApplied: estimation.rules_applied,
    policySummary: verification.policy_summary,
    available: verification.available,
    audit,
    received: verification.received ?? null,
    stageChecks: verification.stage_checks ?? null,
    escalation: detail.escalation ?? null,
    trailVersion: `${header.log_count ?? 0}:${header.handoff_count ?? 0}`,
  };
}
