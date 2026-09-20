"use client";

import type { Escalation } from "@/lib/api-types";
import { Button } from "@/components/ui/primitives";

const ROUTES: Record<Escalation["routed_to"], string> = {
  OUTREACH: "Outreach",
  CONTROLLER: "the Controller",
  BLOCKED: "Blocked",
};

/**
 * Shown when the reader removed files and what is left is not enough to accrue:
 * the case does not guess, it is routed on and says what is missing. It comes
 * from the backend's own escalation, never from the UI.
 */
export function EscalationBanner({
  escalation,
  onRestore,
  pending = false,
}: {
  escalation: Escalation;
  onRestore?: () => void;
  pending?: boolean;
}) {
  return (
    <div
      role="status"
      className="mx-[34px] mb-3 flex flex-wrap items-start justify-between gap-x-6 gap-y-2 rounded-lg border border-[#EBD9A8] bg-[#FBF5E6] px-4 py-3"
    >
      <div className="min-w-0 flex-1">
        <div className="text-ui font-medium text-[#6E4F0C]">
          Not enough information{escalation.missing.length > 0 ? `: ${escalation.missing.join(", ")} not supported` : ""}.
          Escalated to {ROUTES[escalation.routed_to]}.
        </div>
        <div className="mt-1 text-meta leading-[1.55] text-[#8A6516] text-pretty">{escalation.message}</div>
      </div>
      {onRestore && (
        <Button className="flex-none text-meta" disabled={pending} onClick={onRestore}>
          {pending ? "Restoring..." : "Restore files"}
        </Button>
      )}
    </div>
  );
}
