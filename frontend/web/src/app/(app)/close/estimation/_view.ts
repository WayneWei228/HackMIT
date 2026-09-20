import type { Header, ObligationDetail, Row } from "@/lib/api-types";
import { formatMoney, formatSigned } from "@/lib/money";
import { routes } from "@/lib/routes";
import { periodLabel } from "@/lib/time";

export type InputCardView = {
  label: string;
  value: string;
  sub: string | null;
  icon: "doc" | "calendar";
  /** Route the sub-label links to, when it names another screen. */
  linkTo: string | null;
  /** First step at which this card is revealed. */
  revealAt: number;
};

export type AdjustmentView = { label: string; result: string };
export type JournalLineView = { side: string; account: string; amount: string };

export type EstimationScreenView = {
  obligationId: string;
  header: Header;
  hasEstimate: boolean;
  inputs: InputCardView[];
  footnote: string;
  coverageText: string;
  rateText: string;
  calc: { done: string; rows: Row[]; total: Row };
  adjustments: AdjustmentView[];
  adjustmentsDone: string;
  finalText: string;
  amount: string;
  recommendation: (Row & { tone?: "accent" })[];
  note: string;
  journal: JournalLineView[];
  closing: string;
};

const REVEAL = [1, 1, 2, 2, 3];
const LINKS: Record<string, string> = {
  "Obligation basis": routes.obligation,
  "Prior accrual": routes.evidence,
};
const ADJUSTMENT_CHECKS = ["credits_and_refunds", "prepaid_amounts", "partial_period_offsets"];

export function buildEstimationView(detail: ObligationDetail): EstimationScreenView {
  const { estimation, obligation, header } = detail;
  const has = estimation.available && estimation.amount !== null;
  const amount = formatMoney(estimation.amount);
  const prior = header.difference;
  const period = periodLabel(header.period);
  const coverage = estimation.checks.find((check) => check.name === "coverage_period");
  const days = coverage?.detail.days;

  const noEstimate =
    estimation.outcome_note ?? "No recommendation: the evidence does not support an estimate.";
  const rules = estimation.rules_applied
    .map((rule) => `Learned rule ${rule.learning_id} applied: ${rule.description}`)
    .join(" ");

  return {
    obligationId: header.obligation_id,
    header,
    hasEstimate: has,
    inputs: estimation.inputs.map<InputCardView>((input, index) => ({
      label: input.label,
      value: /^-?\d+\.\d{2}$/.test(input.value) ? formatMoney(input.value) : input.value,
      sub: input.sub,
      icon: input.label === "Coverage period" ? "calendar" : "doc",
      linkTo: LINKS[input.label] ?? null,
      revealAt: REVEAL[index] ?? 3,
    })),
    footnote: has ? "Obligation basis confirmed" : "Waiting on evidence",
    coverageText: `Service period is ${obligation.service_period}${days ? ` (${String(days)} days)` : ""}.`,
    rateText: has
      ? [`${estimation.method_label}: ${estimation.expression}.`, rules].filter(Boolean).join(" ")
      : noEstimate,
    calc: {
      done: has ? `${estimation.expression} = ${amount}.` : noEstimate,
      rows: estimation.calc_rows.map((row) => ({
        label: row.label,
        value: /^-?\d+\.\d{2}$/.test(row.value) ? formatMoney(row.value) : row.value,
      })),
      total: { label: "Base amount", value: amount },
    },
    adjustments: ADJUSTMENT_CHECKS.flatMap((name) => {
      const check = estimation.checks.find((candidate) => candidate.name === name);
      return check ? [{ label: check.label, result: check.result }] : [];
    }),
    adjustmentsDone: estimation.warnings.length
      ? estimation.warnings.join(" ")
      : "No credits, prepaid amounts, or offsets apply.",
    finalText: has
      ? `Recommending ${amount} accrual${prior ? `, ${formatSigned(prior)} on the prior close` : ""}.`
      : noEstimate,
    amount,
    recommendation: estimation.recommendation.map((row) => ({
      label: row.label,
      value:
        row.label === "Compared to prior" && /^[+-]?\d+\.\d{2}$/.test(row.value)
          ? formatSigned(row.value)
          : row.value,
      tone: row.label === "Compared to prior" ? ("accent" as const) : undefined,
    })),
    note: has
      ? `Amount comes from ${estimation.method_label?.toLowerCase()}: ${estimation.expression}.`
      : noEstimate,
    journal: (estimation.entries[0]?.lines ?? []).map((line) => ({
      side: line.side,
      account: `${line.account} · ${line.account_name}`,
      amount: formatMoney(line.amount),
    })),
    closing: has
      ? `Recommendation ready · ${amount} accrual for ${period}`
      : `No recommendation · waiting for evidence for ${period}`,
  };
}
