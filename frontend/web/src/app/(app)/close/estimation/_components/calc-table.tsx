"use client";

import { useEstimationScreen } from "./screen-context";

/** Body of the calculation step: the workpaper's own arithmetic rows, whatever the method. */
export function CalcTable() {
  const { calc } = useEstimationScreen();

  return (
    <div className="pt-[7px] pr-1 pl-[27px]">
      <div className="text-sm leading-[1.65] text-pretty break-words text-muted-4">{calc.done}</div>
      <div className="mt-3 rounded-lg bg-rail-alt px-[15px] py-[13px]">
        {calc.rows.map((row) => (
          <div
            key={row.label}
            className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3.5 py-[5px]"
          >
            <span className="min-w-0 text-meta leading-[normal] text-muted-4">{row.label}</span>
            <span className="text-right text-meta leading-[normal] text-ink tabular-nums">{row.value}</span>
          </div>
        ))}

        <div className="my-[9px] h-px bg-[#E4E4DC]" />

        <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3.5">
          <span className="text-sm leading-[normal] font-medium text-ink">{calc.total.label}</span>
          <span className="font-display text-[17px] leading-[normal] text-ink-deep">{calc.total.value}</span>
        </div>
      </div>
    </div>
  );
}
