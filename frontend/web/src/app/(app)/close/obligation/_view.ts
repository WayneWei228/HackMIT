import type { Header, ObligationDetail } from "@/lib/api-types";
import { formatMoney, formatSigned } from "@/lib/money";
import { periodLabel } from "@/lib/time";

import { FINAL_STEP, type AnalysisCheck } from "./_data";

export type ScreenFact = {
  label: string;
  amount: string;
  source: string;
  /** Step at which the fact lands in the panel. */
  appearsAt: number;
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
  attributesAppearAt: number;
  intro: string;
  /** The words each check reports once the agent has its answer. */
  narrative: {
    contractTerms: string;
    servicePeriod: string;
    eligibility: string;
    amount: string;
  };
  conclusion: { amountLabel: string; amount: string; note: string };
  rows: ConclusionRow[];
  closing: string;
};

/** The panel has room for this many facts; the rest stay on the Evidence screen. */
const MAX_FACTS = 4;

const CONFIDENCE = {
  SUFFICIENT: { value: "High", width: "82%" },
  CONFLICTING: { value: "Low", width: "34%" },
} as const;

export function buildObligationView(detail: ObligationDetail): ObligationScreenView {
  const { obligation, header, evidence } = detail;
  const amount = obligation.estimated_amount;
  const shown = obligation.facts.slice(0, MAX_FACTS);
  const period = periodLabel(header.period);

  const facts = shown.map<ScreenFact>((fact, index) => ({
    label: fact.label,
    amount: fact.value || fact.label,
    source: [fact.file_name, fact.page ? `p. ${fact.page}` : null].filter(Boolean).join(" · "),
    appearsAt: 1 + Math.min(index, 2),
  }));

  const signalText = obligation.signals.length
    ? obligation.signals.map((s) => `${s.name} = ${s.value}`).join("; ")
    : "no structural signal";
  const eligibility =
    obligation.accrual_required === null
      ? "Waiting for the invoice search."
      : obligation.accrual_required
        ? "No invoice covers the period, so an accrual is required."
        : "An invoice already covers the period, so no accrual is needed.";

  const amountText = !amount
    ? "No amount yet: the evidence does not support an estimate."
    : `${formatMoney(amount)} by ${obligation.basis?.toLowerCase() ?? "estimate"}${
        obligation.change_vs_prior
          ? `, ${formatSigned(obligation.change_vs_prior)} on the prior accrual`
          : ""
      }.`;

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
    attributesAppearAt: 3,
    intro: `Applying accounting logic to determine the ${period} obligation.`,
    narrative: {
      contractTerms: `Classified as ${obligation.purchase_type_label.toLowerCase()} from ${signalText}.`,
      servicePeriod: `${obligation.service_period}.`,
      eligibility: `${obligation.invoice_note ?? ""} ${eligibility}`.trim(),
      amount: amountText,
    },
    conclusion: {
      amountLabel: "Estimated obligation",
      amount: formatMoney(amount),
      note: amount
        ? "Final amount will be passed to the Estimation agent for journal construction."
        : "There is no amount yet. Estimation cannot run until the evidence is complete.",
    },
    rows: [
      { kind: "text", label: "Service period", value: obligation.service_period, tone: "ink" },
      { kind: "text", label: "Basis", value: obligation.basis ?? "Not estimated", tone: "ink" },
      {
        kind: "text",
        label: "Change vs. prior",
        value: formatSigned(obligation.change_vs_prior),
        tone: "accent",
      },
      {
        kind: "text",
        label: "Accrual required",
        value:
          obligation.accrual_required === null ? "-" : obligation.accrual_required ? "Yes" : "No",
        tone: "ink",
      },
      { kind: "confidence", label: "Confidence", ...confidence },
    ],
    closing: amount
      ? `Obligation determined · ${formatMoney(amount)} for ${period}`
      : `Obligation reviewed · no amount for ${period} yet`,
  };
}

/** The four analysis checks; a check's body is what it says at a given step of the run. */
export function buildChecks(narrative: ObligationScreenView["narrative"]): AnalysisCheck[] {
  return [
    {
      label: "Contract terms",
      body: () => narrative.contractTerms,
      bodyDuration: 0.34,
    },
    {
      label: "Service period",
      body: () => narrative.servicePeriod,
      bodyDuration: 0.34,
    },
    {
      label: "Accrual eligibility",
      body: (step) =>
        step >= 10
          ? narrative.eligibility
          : "Assessing whether service was received and payment is incurred...",
      subChecks: [
        "Search AP for an invoice",
        "Check the evidence status",
        "Confirm the purchase type",
        "Confirm the service window",
      ],
      bodyDuration: 0.38,
    },
    {
      label: "Obligation amount",
      body: (step) =>
        step >= FINAL_STEP
          ? narrative.amount
          : "Computing from the governing terms and the service period...",
      pending: { label: "Waiting", until: 10 },
      bodyDuration: 0.34,
    },
  ];
}
