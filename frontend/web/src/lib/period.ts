/**
 * Periods.
 *
 * A close is scoped to one month. The backend names a month `"YYYY-MM"`; the
 * product says "December 2026" - and, until this round, said it in hardcoded
 * copy on six screens. Everything a screen needs to know about a month is
 * derived here so no screen has to know what month it is.
 */

/** The sentinel the period filter uses for "do not scope to a month". */
export const ALL_PERIODS = "All months";

export type PeriodState = "NOT_RUN" | "CLOSED" | "SETTLED" | string;

/** One month, as `GET /api/periods` describes it. Every field is optional: */
/* the endpoint is young and the UI must render whatever arrives. */
export type PeriodInfo = {
  period: string;
  label?: string;
  state?: PeriodState;
  cases?: number;
  accrued_total?: number;
  true_up_total?: number;
  documents?: number;
  can_close?: boolean;
  can_settle?: boolean;
};

const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

/** `"2026-12"` -> `"December 2026"`. Anything else comes back untouched. */
export function periodLabel(period: string | null | undefined): string {
  if (!period) return ALL_PERIODS;
  if (period === ALL_PERIODS) return ALL_PERIODS;
  const match = /^(\d{4})-(\d{2})$/.exec(period);
  if (!match) return period;
  const month = MONTHS[Number(match[2]) - 1];
  return month ? `${month} ${match[1]}` : period;
}

/** `"2026-12"` -> `"December"`, for places with no room for the year. */
export function periodMonthLabel(period: string | null | undefined): string {
  const label = periodLabel(period);
  return label.split(" ")[0] ?? label;
}

/** The label a month should carry, preferring the API's own. */
export function infoLabel(info: PeriodInfo): string {
  return info.label || periodLabel(info.period);
}

/** How a month's state reads in the UI. */
export function stateLabel(state: PeriodState | undefined): string {
  switch (state) {
    case "NOT_RUN":
      return "Not run";
    case "CLOSED":
      return "Closed";
    case "SETTLED":
      return "Settled";
    default:
      return state ? String(state) : "Unknown";
  }
}

/** Newest month first - the order every menu in the product lists them in. */
export function sortPeriods(periods: readonly PeriodInfo[]): PeriodInfo[] {
  return [...periods].sort((a, b) => b.period.localeCompare(a.period));
}
