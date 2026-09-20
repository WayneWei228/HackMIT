import type {
  Escalation,
  Header,
  ObligationDetail,
  Received,
  StageCheck,
} from "@/lib/api-types";
import { formatMoney, formatSigned } from "@/lib/money";
import { stageDone } from "@/lib/trail";

export type ScreenFact = {
  label: string;
  amount: string;
  source: string;
};

export type ConclusionRow =
  | { kind: "text"; label: string; value: string; tone: "ink" | "accent" }
  | { kind: "confidence"; label: string; value: string; width: string };

export type ObligationScreenView = {
  obligationId: string;
  header: Header;
  evidenceInputsLabel: string;
  sourceDocumentsLabel: string;
  facts: ScreenFact[];
  attributes: { label: string; value: string }[];
  /** What this stage received from the Evidence agent, straight from the backend. */
  received: Received | null;
  /** The checks the agents ran, one row per real check; null when the backend sent none. */
  checks: StageCheck[] | null;
  /** The number the agent stands behind: shown only once Estimation has really produced it. */
  conclusion: { amountLabel: string; amount: string; note: string | null };
  rows: ConclusionRow[];
  escalation: Escalation | null;
  /** Changes whenever the case's trail grows, so it is read again. */
  trailVersion: string;
};

/** The panel has room for this many facts; the rest stay on the Evidence screen. */
const MAX_FACTS = 4;

const CONFIDENCE = {
  SUFFICIENT: { value: "High", width: "82%" },
  CONFLICTING: { value: "Low", width: "34%" },
} as const;

export function buildObligationView(detail: ObligationDetail): ObligationScreenView {
  const { obligation, header, evidence } = detail;
  /* An amount is drawn only after the stage that produces it has really run. */
  const estimated = stageDone(header, "estimation");
  const amount = estimated ? obligation.estimated_amount : null;
  const change = estimated ? obligation.change_vs_prior : null;

  const facts = obligation.facts.slice(0, MAX_FACTS).map<ScreenFact>((fact) => ({
    label: fact.label,
    amount: fact.value || fact.label,
    source: [fact.file_name, fact.page ? `p. ${fact.page}` : null].filter(Boolean).join(" · "),
  }));

  const confidence =
    CONFIDENCE[obligation.evidence_status as keyof typeof CONFIDENCE] ??
    (obligation.evidence_status === "SUFFICIENT"
      ? CONFIDENCE.SUFFICIENT
      : { value: "Low", width: "34%" });

  return {
    obligationId: header.obligation_id,
    header,
    evidenceInputsLabel: `${evidence.documents.length} evidence inputs`,
    sourceDocumentsLabel: `${evidence.documents.length} source documents`,
    facts,
    attributes: [
      { label: "Service period", value: obligation.service_period },
      { label: "Service type", value: obligation.purchase_type_label },
    ],
    received: obligation.received ?? null,
    checks: obligation.stage_checks ?? null,
    conclusion: {
      amountLabel: "Estimated obligation",
      amount: formatMoney(amount),
      note: obligation.rationale,
    },
    rows: [
      { kind: "text", label: "Service period", value: obligation.service_period, tone: "ink" },
      {
        kind: "text",
        label: "Basis",
        value: estimated ? (obligation.basis ?? "-") : "-",
        tone: "ink",
      },
      { kind: "text", label: "Change vs. prior", value: formatSigned(change), tone: "accent" },
      {
        kind: "text",
        label: "Accrual required",
        value:
          obligation.accrual_required === null ? "-" : obligation.accrual_required ? "Yes" : "No",
        tone: "ink",
      },
      { kind: "confidence", label: "Confidence", ...confidence },
    ],
    escalation: detail.escalation ?? null,
    trailVersion: `${header.log_count ?? 0}:${header.handoff_count ?? 0}`,
  };
}
