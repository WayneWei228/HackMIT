"use client";

import { ScreenState } from "@/components/ui/screen-state";
import { ALL_PERIODS, periodLabel } from "@/lib/period";

/**
 * Shown when the search box and the filters between them exclude every case.
 *
 * This is the *filter* empty state: the month has rows, none of them match.
 * `PeriodEmptyState` below is the other one - the month itself is empty.
 */
export function CasesEmptyState({ onClear }: { onClear: () => void }) {
  return (
    <ScreenState
      title="No cases match"
      body="Try a different search term, or clear the filters."
      actions={[{ label: "Clear filters", onClick: onClear }]}
      className="mt-4"
    />
  );
}

/**
 * Shown when the backend answered for this month and had nothing in it.
 *
 * Nothing is ever pre-loaded: a month holds no cases until its close has been
 * run over that month's output files. So an empty month is not a failure and
 * not an absence of data - it is a month that has not been run, and the thing
 * to say is how to run it.
 */
export function PeriodEmptyState({
  period,
  actionLabel,
  reason,
  blockedBy,
  busy,
  onRun,
}: {
  /** The selected month, `ALL_PERIODS`, or `null` before one is resolved. */
  period: string | null;
  /** The run this month will accept, or `null` when it will accept none. */
  actionLabel: string | null;
  /** The API's own explanation, when it has refused and said why. */
  reason: string | null;
  /**
   * The month standing in the way, when this one cannot run yet.
   *
   * Months close in order, so a month with nothing to offer is not a dead
   * end - it is waiting on an earlier one. Saying which, and linking to it,
   * is the difference between a locked door and a signposted one.
   */
  blockedBy: { label: string; href: string } | null;
  busy: boolean;
  onRun: () => void;
}) {
  const scoped = period !== null && period !== ALL_PERIODS;
  const title = scoped
    ? `No close has been run for ${periodLabel(period)} yet`
    : "No close has been run yet";

  const body = actionLabel
    ? "Every case on this screen is built from that month's output files when the close runs."
    : blockedBy
      ? `${scoped ? periodLabel(period) : "This month"} cannot run yet - close ${blockedBy.label} first. Months close in order.`
      : (reason ??
        "This month cannot be run from here yet - an earlier month has to close first.");

  return (
    <ScreenState
      title={title}
      body={body}
      /* A refusal that arrived from a button press is already on screen in
         the run strip above; repeating it here would say it twice. */
      actions={
        actionLabel && !busy
          ? [{ label: actionLabel, onClick: onRun }]
          : blockedBy
            ? [{ label: `Go to ${blockedBy.label}`, href: blockedBy.href }]
            : []
      }
      className="mt-4"
    />
  );
}
