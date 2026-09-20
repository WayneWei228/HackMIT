"use client";

import { Button } from "@/components/ui/primitives";
import {
  bringInInvoice,
  deliverReply,
  deliverVendorReply,
  expireOutreach,
  getClose,
  rewindOutreach,
} from "@/lib/api";
import type { TimeAction } from "@/lib/api-types";
import { useCaseId } from "@/lib/case-context";
import { useCaseData } from "@/lib/case-data";
import { useCaseRunner } from "@/lib/case-runner";
import { formatStamp } from "@/lib/time";
import { useApiAction } from "@/lib/use-api-action";

const TAKE: Record<TimeAction["kind"], (id: string) => Promise<unknown>> = {
  DELIVER_REPLY: deliverReply,
  EXPIRE_OUTREACH: expireOutreach,
  BRING_IN_INVOICE: bringInInvoice,
  DELIVER_VENDOR_REPLY: deliverVendorReply,
};

/** "Jan 31, 2027": the demo day a case moves to. */
export function momentLabel(iso: string): string {
  return formatStamp(iso).date;
}

/**
 * The one thing time can do for the open case, taken on that case alone. An owner's reply leaves the
 * case ready to resume, so the run carries it on stage by stage; the others finish in the call.
 */
export function useTimeAction() {
  const id = useCaseId();
  const { detail } = useCaseData(id);
  const runner = useCaseRunner();
  const { run, pending, error } = useApiAction();
  const action = detail?.next_time_action ?? null;
  const others = detail?.other_time_actions ?? [];
  const canRewind = detail?.can_rewind ?? false;
  const otherPath = canRewind ? (detail?.other_path ?? null) : null;

  /* Either way the email is settled, the case is left ready to resume, and the run carries it on. */
  async function take(chosen: TimeAction | null = action, rewindFirst = false) {
    if (!id || !chosen) return;
    const done = await run(async () => {
      if (rewindFirst) await rewindOutreach(id);
      await TAKE[chosen.kind](id);
    });
    if (
      !done ||
      (chosen.kind !== "DELIVER_REPLY" && chosen.kind !== "EXPIRE_OUTREACH")
    )
      return;
    const row = (await getClose()).cases.find((c) => c.obligation_id === id);
    if (row?.current_agent) {
      runner.start([
        {
          obligationId: id,
          completed: row.stages_completed ?? [],
          agent: row.current_agent,
          reveal: true,
        },
      ]);
    }
  }

  async function rewind() {
    if (id) await run(() => rewindOutreach(id));
  }

  const tryOther = () => take(otherPath, true);

  return {
    action,
    others,
    canRewind,
    otherPath,
    take,
    tryOther,
    rewind,
    pending,
    error,
  };
}

/** Under a case's ribbon: what happens next in its own timeline, and the button that makes it happen. */
export function NextTimeAction({ className }: { className?: string }) {
  const {
    action,
    others,
    canRewind,
    otherPath,
    take,
    tryOther,
    rewind,
    pending,
    error,
  } = useTimeAction();
  if (!action && !canRewind) return null;
  return (
    <div
      role="group"
      aria-label="Next step in this case's timeline"
      className={`mt-2.5 flex flex-wrap items-center justify-between gap-x-6 gap-y-2.5 rounded-lg border border-accent-line-2 bg-accent-tint px-3.5 py-3 ${className ?? ""}`}
    >
      <div className="min-w-0 flex-[1_1_360px]">
        <div className="text-eyebrow font-medium tracking-caps text-accent-deep uppercase">
          Next in this case&apos;s timeline
        </div>
        <div className="mt-1 text-ui leading-[1.45] text-ink-2 text-pretty">
          {action ? (
            <>
              {action.detail}{" "}
              <span className="whitespace-nowrap text-muted-3">
                Moves this case to {momentLabel(action.moves_to)}.
              </span>
            </>
          ) : otherPath ? (
            <>
              <span className="font-medium text-ink">
                Other scenario: {otherPath.label}.
              </span>{" "}
              {otherPath.detail}
            </>
          ) : (
            "This case has taken a path at its email. Rewind to take the other one."
          )}
        </div>
        {pending && canRewind && (
          <div className="mt-1 text-meta text-muted-3">
            Replaying this case from day one with the live model. This can take
            up to a minute.
          </div>
        )}
        {error && <div className="mt-1 text-meta text-[#A4452F]">{error}</div>}
      </div>
      <div className="flex flex-wrap items-center gap-2.5">
        {canRewind && otherPath && (
          <Button
            variant="solid"
            disabled={pending}
            onClick={() => void tryOther()}
          >
            {pending ? "Working..." : "Try the other scenario"}
          </Button>
        )}
        {canRewind && (
          <Button
            variant="secondary"
            disabled={pending}
            onClick={() => void rewind()}
          >
            Rewind to the email
          </Button>
        )}
        {action && (
          <Button
            variant="solid"
            disabled={pending}
            onClick={() => void take(action)}
          >
            {pending ? "Working..." : action.label}
          </Button>
        )}
        {others.map((other) => (
          <Button
            key={other.kind}
            variant="secondary"
            disabled={pending}
            onClick={() => void take(other)}
          >
            {other.label}
          </Button>
        ))}
      </div>
    </div>
  );
}
