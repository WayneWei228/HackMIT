"use client";

import { useStageResting } from "@/lib/stage-reveal";
import { cn } from "@/lib/cn";

/**
 * Rows still to come while a stage's agent works: bars with no words in them,
 * because nothing has been decided yet. They give way to the agent's real rows.
 */
export function PendingRows({ count = 3, className }: { count?: number; className?: string }) {
  const resting = useStageResting();
  if (resting) {
    return (
      <p className={cn("text-sm leading-[1.6] text-pretty text-faint-2", className)}>
        Nothing has run for this stage: the case is waiting on someone else.
      </p>
    );
  }
  return (
    <div aria-hidden="true" className={cn("flex flex-col gap-3.5", className)}>
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="flex items-center gap-3">
          <span
            className="h-[17px] w-[17px] flex-none animate-pulse rounded-full border border-rule"
            style={{ animationDelay: `${i * 120}ms` }}
          />
          <span
            className="h-[10px] animate-pulse rounded-sm bg-wash-deep"
            style={{ width: `${72 - i * 14}%`, animationDelay: `${i * 120}ms` }}
          />
        </div>
      ))}
    </div>
  );
}
