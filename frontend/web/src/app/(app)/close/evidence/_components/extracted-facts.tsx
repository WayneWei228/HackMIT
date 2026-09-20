"use client";

import { SectionLabel } from "@/components/ui/primitives";
import { useRevealingStage } from "@/lib/stage-reveal";

import { RAIL } from "../_data";
import type { FactRow } from "../_view";

/**
 * The fact set the evidence agent handed on, exactly as it returned it. Each row
 * is a two-column grid with `min-width: 0` tracks, so a long value wraps under
 * its label's height instead of drawing over it.
 */
export function ExtractedFacts({ facts }: { facts: readonly FactRow[] }) {
  const reading = useRevealingStage() === "evidence";
  return (
    <>
      <div className="mt-8 h-px bg-sunk" />
      <SectionLabel className="mt-[22px] text-[10.5px] text-faint">
        {RAIL.factsLabel}
      </SectionLabel>

      <div className="mt-3 flex flex-col gap-px">
        {facts.length === 0 && reading && (
          <div className="flex items-center gap-2.5 py-2 text-ui text-faint-2">
            <span aria-hidden="true" className="h-[7px] w-[7px] flex-none animate-pulse rounded-full bg-accent" />
            Reading the documents
          </div>
        )}
        {facts.length === 0 && !reading && (
          <div className="py-2 text-ui text-faint-2">No facts were extracted.</div>
        )}
        {facts.map((fact) => (
          <div
            key={fact.id}
            title={fact.citation || undefined}
            className="-mx-2 grid grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)] items-baseline gap-x-4 rounded-md p-2"
          >
            <span className="min-w-0 text-ui leading-[1.4] text-ink-2 break-words">{fact.label}</span>
            <span className="min-w-0 text-right text-ui leading-[1.4] text-ink break-words tabular-nums">
              {fact.value}
            </span>
          </div>
        ))}
      </div>
    </>
  );
}
