"use client";

import { useCallback, useState } from "react";

import {
  type BuildStepDef,
  autoOpenStep,
  bodyText,
  buildStepStates,
} from "../_data";
import { AdjustmentChecks } from "./adjustment-checks";
import { BuildStep } from "./build-step";
import { CalcTable } from "./calc-table";
import { useEstimationData } from "./data-context";

/**
 * Middle column: the agent's reasoning, one rung per build step. Until
 * somebody clicks a step the panel follows the run, opening whichever step is
 * currently active.
 */
export function EstimateBuildPanel({
  step,
  runId,
}: {
  step: number;
  runId: number;
}) {
  const { BUILD_BLURB, BUILD_STEPS } = useEstimationData().data;

  /** `null` means "follow the run"; `-1` means the reader closed them all. */
  const [opened, setOpened] = useState<number | null>(null);
  const [lastRun, setLastRun] = useState(runId);

  // A replay restarts the run, so the panel goes back to following it.
  if (lastRun !== runId) {
    setLastRun(runId);
    setOpened(null);
  }

  const states = buildStepStates(step, BUILD_STEPS.length);
  const open =
    opened === null ? autoOpenStep(step, BUILD_STEPS.length) : opened;

  const toggle = useCallback(
    (i: number) => setOpened((current) => (current === i ? -1 : i)),
    [],
  );

  return (
    <section className="min-h-full rounded-xl border border-divider bg-panel px-[22px] pt-5 pb-[22px] shadow-[var(--shadow-tile)]">
      <div className="font-display text-2xl leading-[normal] text-ink-deep">
        Estimate build
      </div>
      {BUILD_BLURB ? (
        <div className="mt-1.5 text-sm leading-[1.6] text-pretty text-faint">
          {BUILD_BLURB}
        </div>
      ) : null}

      <div className="mt-5">
        {BUILD_STEPS.map((definition, i) => (
          <BuildStep
            key={`${definition.kind}-${i}`}
            n={definition.n}
            title={definition.title}
            state={states[i]}
            open={open === i}
            last={i === BUILD_STEPS.length - 1}
            tallBody={definition.tallBody}
            waiting={
              definition.waitingUntil === undefined
                ? undefined
                : step < definition.waitingUntil
            }
            onToggle={() => toggle(i)}
          >
            <StepBody definition={definition} step={step} />
          </BuildStep>
        ))}
      </div>
    </section>
  );
}

/**
 * A step's body: the sentence the backend wrote for it, plus the table that
 * belongs to its kind. Nothing here composes a sentence of its own.
 */
function StepBody({
  definition,
  step,
}: {
  definition: BuildStepDef;
  step: number;
}) {
  const text = bodyText(definition, step);

  if (definition.kind === "calc") return <CalcTable step={step} text={text} />;
  if (definition.kind === "adjustments") {
    return <AdjustmentChecks step={step} text={text} />;
  }
  if (!text) return null;
  return (
    <div className="pt-[7px] pr-[26px] pl-[27px] text-sm leading-[1.65] text-pretty text-muted-4">
      {text}
    </div>
  );
}
