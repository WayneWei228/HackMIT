import type {
  Escalation,
  Header,
  ObligationDetail,
  Received,
  Row,
  StageCheck,
} from "@/lib/api-types";
import { formatMoney, formatSigned } from "@/lib/money";
import { routes } from "@/lib/routes";

export type InputCardView = {
  label: string;
  value: string;
  sub: string | null;
  icon: "doc" | "calendar";
  /** Route the sub-label links to, when it names another screen. */
  linkTo: string | null;
};

export type AdjustmentView = { label: string; result: string };

/**
 * One rung of the estimate build. The list is the workpaper's own trace: a step
 * exists only when the estimator recorded the check for it, so a vendor whose
 * method has no adjustment or prior-close check simply has no such step.
 */
export type BuildStepView = {
  key: string;
  title: string;
  kind: "text" | "calc" | "adjustments";
  /** What the estimator recorded for this step. */
  body: string;
  /** The stage check the agent raised for this step, when it raised one. */
  status: StageCheck["status"] | null;
};
export type JournalLineView = { side: string; account: string; amount: string };

export type EstimationScreenView = {
  obligationId: string;
  header: Header;
  hasEstimate: boolean;
  inputs: InputCardView[];
  /** One line from the backend about the basis; null when it sent none. */
  footnote: string | null;
  calc: { done: string; rows: Row[]; total: Row };
  adjustments: AdjustmentView[];
  /** The rungs of the estimate build, in the order the estimator recorded them. */
  steps: BuildStepView[];
  /** The step to open first: the first one the agent flagged, else the calculation. */
  openStep: string | null;
  amount: string;
  recommendation: (Row & { tone?: "accent" })[];
  note: string;
  journal: JournalLineView[];
  received: Received | null;
  stageChecks: StageCheck[] | null;
  escalation: Escalation | null;
  trailVersion: string;
};

const LINKS: Record<string, string> = {
  "Obligation basis": routes.obligation,
  "Prior accrual": routes.evidence,
};
/** Checks that adjust the base amount; they are grouped under one "Adjustments" rung. */
const ADJUSTMENT_CHECKS = new Set(["credits_and_refunds", "prepaid_amounts", "partial_period_offsets"]);

const isMoney = (value: string) => /^-?\d+\.\d{2}$/.test(value);

/** The stage check the Estimation agent raised for a workpaper check, e.g. EST-COVERAGE_PERIOD. */
function stageCheckFor(
  stageChecks: readonly StageCheck[] | undefined,
  name: string,
): StageCheck | undefined {
  const wanted = `EST-${name.toUpperCase()}`;
  return stageChecks?.find((check) => check.check_id === wanted);
}

/**
 * The rungs of the estimate build, taken from the workpaper's trace in the order
 * the estimator recorded it. Nothing is assumed: a method without a prior-close
 * or adjustment check has no such rung, and an estimate that was never produced
 * is shown as the stage checks the agent raised instead.
 */
function buildSteps(
  estimation: ObligationDetail["estimation"],
  has: boolean,
  finalBody: string,
): BuildStepView[] {
  const stageChecks = estimation.stage_checks;
  const steps: BuildStepView[] = [];
  let adjustmentsAdded = false;
  let calcAdded = false;

  const addCalc = () => {
    if (calcAdded || estimation.calc_rows.length === 0) return;
    calcAdded = true;
    steps.push({
      key: "calc",
      title: estimation.method_label ?? "Calculation",
      kind: "calc",
      body: estimation.expression ?? "",
      status: null,
    });
  };

  for (const check of estimation.checks) {
    if (ADJUSTMENT_CHECKS.has(check.name)) {
      if (adjustmentsAdded) continue;
      adjustmentsAdded = true;
      const group = estimation.checks.filter((c) => ADJUSTMENT_CHECKS.has(c.name));
      const flagged = group
        .map((c) => stageCheckFor(stageChecks, c.name))
        .find((c) => c?.status === "FLAG");
      steps.push({
        key: "adjustments",
        title: "Adjustments",
        kind: "adjustments",
        body: estimation.warnings.join(" "),
        status: flagged?.status ?? (group.length > 0 ? "PASS" : null),
      });
      continue;
    }
    steps.push({
      key: check.name,
      title: check.label,
      kind: "text",
      body: check.result,
      /* The estimator raises its amount-and-method check as EST-RATE. */
      status: stageCheckFor(stageChecks, check.name === "rate_applied" ? "rate" : check.name)?.status ?? null,
    });
    if (check.name === "rate_applied") addCalc();
  }
  addCalc();

  if (has && estimation.recommendation.length > 0) {
    steps.push({ key: "final", title: "Recommendation", kind: "text", body: finalBody, status: null });
  }

  /* No workpaper: the agent stopped, so the rungs are the checks it raised. */
  if (steps.length === 0) {
    for (const check of stageChecks ?? []) {
      steps.push({
        key: check.check_id,
        title: check.label,
        kind: "text",
        body: check.body,
        status: check.status,
      });
    }
  }
  return steps;
}

export function buildEstimationView(detail: ObligationDetail): EstimationScreenView {
  const { estimation, header } = detail;
  const has = estimation.available && estimation.amount !== null;
  const amount = formatMoney(estimation.amount);
  const prior = header.difference;
  const stop = estimation.stage_checks?.find((check) => check.status === "FLAG");
  const noEstimate = estimation.outcome_note ?? stop?.body ?? "";
  const rules = estimation.rules_applied
    .map((rule) => `Learned rule ${rule.learning_id} applied: ${rule.description}`)
    .join(" ");
  const finalBody = has
    ? `${amount}${prior ? `, ${formatSigned(prior)} on the prior close` : ""}. ${rules}`.trim()
    : noEstimate;
  const steps = buildSteps(estimation, has, finalBody);
  const opened = steps.find((step) => step.status === "FLAG") ?? steps.find((step) => step.kind === "calc") ?? steps[0];

  return {
    obligationId: header.obligation_id,
    header,
    hasEstimate: has,
    inputs: estimation.inputs.map<InputCardView>((input) => ({
      label: input.label,
      value: isMoney(input.value) ? formatMoney(input.value) : input.value,
      sub: input.sub,
      icon: input.label === "Coverage period" ? "calendar" : "doc",
      linkTo: LINKS[input.label] ?? null,
    })),
    footnote: has && estimation.method_label ? `Basis: ${estimation.method_label}` : null,
    calc: {
      done: has ? `${estimation.expression} = ${amount}.` : noEstimate,
      rows: estimation.calc_rows.map((row) => ({
        label: row.label,
        value: isMoney(row.value) ? formatMoney(row.value) : row.value,
      })),
      total: { label: "Base amount", value: amount },
    },
    adjustments: estimation.checks
      .filter((check) => ADJUSTMENT_CHECKS.has(check.name))
      .map((check) => ({ label: check.label, result: check.result })),
    steps,
    openStep: opened?.key ?? null,
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
    received: estimation.received ?? null,
    stageChecks: estimation.stage_checks ?? null,
    escalation: detail.escalation ?? null,
    trailVersion: `${header.log_count ?? 0}:${header.handoff_count ?? 0}`,
  };
}
