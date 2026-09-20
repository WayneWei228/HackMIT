"use client";

import { motion } from "motion/react";

import { CheckIcon } from "@/components/ui/icons";
import { Button } from "@/components/ui/primitives";
import { advanceToJanuary, advanceToVendorReply } from "@/lib/api";
import type { ClockStop, CloseView } from "@/lib/api-types";
import { useRunner } from "@/lib/case-runner";
import { useClose } from "@/lib/case-data";
import { cn } from "@/lib/cn";
import { transitions } from "@/lib/motion";
import { formatStamp } from "@/lib/time";
import { useApiAction } from "@/lib/use-api-action";

/**
 * Which way time can move next, straight from what the backend allows: January's
 * invoices once the close has run, then the vendors' replies once an email is out.
 */
function nextMove(close: CloseView): { label: string; run: () => Promise<unknown> } | null {
  if (close.actions.can_advance_to_january) {
    return { label: "Advance to January", run: advanceToJanuary };
  }
  if (close.actions.can_advance_to_vendor_reply) {
    return { label: "Advance to vendor reply", run: advanceToVendorReply };
  }
  return null;
}

function disabledHint(close: CloseView): string {
  if (close.phase === "DAY_ONE") return "Start at least one case first";
  return "Nothing more is due";
}

function Dot({ state }: { state: ClockStop["state"] }) {
  if (state === "DONE") {
    return (
      <span className="flex h-[14px] w-[14px] items-center justify-center rounded-full bg-accent-forest text-accent-on-2 transition-colors duration-[380ms]">
        <CheckIcon size={9} />
      </span>
    );
  }
  if (state === "CURRENT") {
    return (
      <span className="relative flex h-[14px] w-[14px] items-center justify-center">
        <span className="animate-pulse-ring absolute inset-0 rounded-full bg-accent/40" />
        <span className="relative flex h-[14px] w-[14px] items-center justify-center rounded-full border-2 border-accent bg-panel">
          <span className="h-[4px] w-[4px] rounded-full bg-accent" />
        </span>
      </span>
    );
  }
  return (
    <span className="h-[14px] w-[14px] rounded-full border border-line-dark bg-panel transition-colors duration-[380ms]" />
  );
}

function Stop({ stop, last }: { stop: ClockStop; last: boolean }) {
  const current = stop.state === "CURRENT";
  return (
    <li
      title={stop.detail ? `${stop.label}: ${stop.detail}` : stop.label}
      className={cn(
        "relative flex gap-2.5 pb-[9px] last:pb-0",
        !current && "[@media(max-height:820px)]:hidden",
      )}
    >
      <div className="relative flex w-[14px] flex-none flex-col items-center pt-px">
        <Dot state={stop.state} />
        {!last && (
          <span
            aria-hidden="true"
            className={cn(
              "absolute top-[18px] -bottom-[9px] w-px transition-colors duration-[380ms]",
              stop.state === "DONE" ? "bg-accent-line" : "bg-line-warm",
            )}
          />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <span
            className={cn(
              "text-ui leading-[1.25] transition-colors duration-[380ms]",
              stop.state === "UPCOMING" ? "text-faint-2" : "text-ink",
              current && "font-medium",
            )}
          >
            {stop.label}
          </span>
          <span className="flex-none text-meta text-faint-2">{stop.date_label}</span>
        </div>
        {current && stop.detail && (
          <div className="mt-0.5 text-meta leading-[1.3] text-muted-3">{stop.detail}</div>
        )}
      </div>
    </li>
  );
}

/**
 * The demo calendar in the sidebar: where the simulated clock is, which moments
 * have passed, and the one control that moves time forward.
 */
export function ClockTimeline({ initial }: { initial: CloseView | null }) {
  const close = useClose(initial);
  const { run, pending, error } = useApiAction();
  const { runs } = useRunner();
  if (!close?.timeline?.length) return null;

  const running = Object.values(runs).some((state) => state.active || state.queued);
  const move = nextMove(close);
  const stamp = formatStamp(close.clock);
  const disabled = move === null || pending || running;

  return (
    <section aria-label="Simulated calendar" className="px-[22px] pb-[14px]">
      <div className="flex items-baseline justify-between">
        <div className="text-eyebrow font-medium tracking-caps-lg text-faint-2">SIMULATED CLOCK</div>
      </div>
      <motion.div
        key={close.clock}
        initial={{ opacity: 0, y: 3 }}
        animate={{ opacity: 1, y: 0 }}
        transition={transitions.slow}
        className="mt-1 text-body text-ink"
      >
        {stamp.date}, {stamp.time}
      </motion.div>
      <ol className="mt-3 flex flex-col">
        {close.timeline.map((stop, i) => (
          <Stop key={stop.key} stop={stop} last={i === close.timeline!.length - 1} />
        ))}
      </ol>
      <Button
        variant="primary"
        className={cn(
          "mt-3 w-full justify-center py-[9px] text-[13px]/[1]",
          disabled && "cursor-not-allowed opacity-45 hover:bg-panel hover:text-accent",
        )}
        disabled={disabled}
        title={move === null ? disabledHint(close) : undefined}
        onClick={() =>
          move &&
          void run(move.run)
        }
      >
        {pending && move ? "Advancing..." : (move?.label ?? "Advance time")}
      </Button>
      {error && <div className="mt-1.5 text-meta text-[#A4452F]">{error}</div>}
    </section>
  );
}
