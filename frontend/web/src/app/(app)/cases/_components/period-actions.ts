import { type PeriodInfo } from "@/lib/period";

/** Which of the two per-month runs the backend will accept right now. */
export type PeriodActions = {
  canClose: boolean;
  canSettle: boolean;
  /** False when the API told us nothing about the month's state. */
  known: boolean;
};

/**
 * What can be run for one month.
 *
 * Every field of `PeriodInfo` is optional, and `GET /api/periods` may not be
 * there at all - `usePeriods` then falls back to the bare month names on
 * `/api/health`. Nothing here may assume a shape: when the API describes the
 * month we follow it exactly, and when it does not we offer both runs and let
 * the backend refuse with the 400 `detail` the strip renders. Guessing "not
 * runnable" would leave a month with no way to be built at all, which is worse
 * than a refusal the reader can read.
 */
export function periodActions(
  info: PeriodInfo | null | undefined,
): PeriodActions {
  const known =
    !!info &&
    (info.can_close !== undefined ||
      info.can_settle !== undefined ||
      info.state !== undefined);
  if (!info || !known) return { canClose: true, canSettle: true, known: false };
  return {
    canClose:
      info.can_close ?? (info.state !== "CLOSED" && info.state !== "SETTLED"),
    canSettle: info.can_settle ?? info.state === "CLOSED",
    known: true,
  };
}
