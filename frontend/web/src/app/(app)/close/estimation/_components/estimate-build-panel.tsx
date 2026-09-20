"use client";

import { useCaseId } from "@/lib/case-context";
import { useCaseUi } from "@/lib/case-store";
import { useRevealSlice } from "@/lib/stage-reveal";

import type { BuildStepView } from "../_view";
import { AdjustmentChecks } from "./adjustment-checks";
import { BuildStep } from "./build-step";
import { CalcTable } from "./calc-table";
import { useEstimationScreen } from "./screen-context";

/**
 * Middle column: the estimate build as the estimator recorded it. The rungs are
 * the workpaper's own trace, so a vendor whose method has different checks shows
 * different steps. Which one is open is kept when the reader leaves and returns.
 */
export function EstimateBuildPanel() {
  const { steps: all, openStep, obligationId } = useEstimationScreen();
  const { count, working } = useRevealSlice(0, all.length);
  const steps = all.slice(0, count);
  const caseId = useCaseId() ?? obligationId;
  /** `undefined` until the reader chooses; then the key they chose, or "" for none. */
  const [chosen, setChosen] = useCaseUi<string | undefined>(caseId, "estimation.open", undefined);
  const open = chosen === undefined ? openStep : chosen === "" ? null : chosen;

  return (
    <section className="min-h-full rounded-xl border border-divider bg-panel px-[22px] pt-5 pb-[22px] shadow-[var(--shadow-tile)]">
      <div className="font-display text-2xl leading-[normal] text-ink-deep">Estimate build</div>

      <div className="mt-5">
        {all.length === 0 && (
          <p className="text-sm text-faint-2">The workpaper recorded no build steps.</p>
        )}
        {steps.map((step, i) => (
          <BuildStep
            key={step.key}
            n={String(i + 1)}
            title={step.title}
            status={step.status}
            open={open === step.key}
            last={i === steps.length - 1 && !working}
            tallBody={step.kind !== "text"}
            onToggle={() => setChosen(open === step.key ? "" : step.key)}
          >
            <StepBody step={step} />
          </BuildStep>
        ))}
        {working && (
          <div className="flex items-center gap-2.5 pt-3 pl-[27px] text-sm text-faint-2">
            <span aria-hidden="true" className="h-[7px] w-[7px] flex-none animate-pulse rounded-full bg-accent" />
            Working on the next step...
          </div>
        )}
      </div>
    </section>
  );
}

function StepBody({ step }: { step: BuildStepView }) {
  return (
    <>
      {step.kind === "text" && step.body && (
        <div className="pt-[7px] pr-[26px] pl-[27px] text-sm leading-[1.65] text-pretty break-words text-muted-4">
          {step.body}
        </div>
      )}
      {step.kind === "calc" && <CalcTable />}
      {step.kind === "adjustments" && <AdjustmentChecks note={step.body} />}
    </>
  );
}
