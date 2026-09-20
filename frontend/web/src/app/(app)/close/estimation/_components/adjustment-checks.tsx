"use client";

import { SubMarker } from "./markers";
import { useEstimationScreen } from "./screen-context";

/** Body of the adjustments step: the adjustment checks the estimator recorded, each with its result. */
export function AdjustmentChecks({ note }: { note: string }) {
  const { adjustments } = useEstimationScreen();

  return (
    <div className="pt-[7px] pr-1 pl-[27px]">
      {note && (
        <div className="text-sm leading-[1.65] text-pretty break-words text-muted-4">{note}</div>
      )}
      <div className="mt-3 flex flex-col gap-[11px] rounded-lg bg-rail-alt px-3.5 py-3">
        {adjustments.map((check) => (
          <div key={check.label} className="grid grid-cols-[auto_minmax(0,1fr)_minmax(0,auto)] items-center gap-[11px]">
            <SubMarker state="done" />
            <span className="min-w-0 text-sm leading-[normal] text-ink-2">{check.label}</span>
            <span className="min-w-0 text-right text-meta leading-[normal] break-words text-faint-2">
              {check.result}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
