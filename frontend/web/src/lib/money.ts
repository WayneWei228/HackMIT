/**
 * Money arrives as Decimal strings ("1400.00", "+200.00") and stays strings.
 * Everything here is string and BigInt work; no number ever holds an amount.
 */

const PATTERN = /^([+-]?)(\d+)(?:\.(\d+))?$/;

function split(value: string): { sign: string; whole: string; cents: string } {
  const match = PATTERN.exec(value.trim());
  if (!match) return { sign: "", whole: value, cents: "" };
  const [, sign, whole, fraction = ""] = match;
  return { sign, whole, cents: fraction.padEnd(2, "0").slice(0, 2) };
}

function group(whole: string): string {
  return whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

/** "1400.00" -> "$1,400"; "11840.50" -> "$11,840.50"; null -> "-". */
export function formatMoney(value: string | null | undefined): string {
  if (value == null || value === "") return "-";
  const { sign, whole, cents } = split(value);
  const tail = cents === "" || /^0+$/.test(cents) ? "" : `.${cents}`;
  return `${sign === "-" ? "-" : ""}$${group(whole)}${tail}`;
}

/** "+200.00" -> "+$200"; "-15.50" -> "-$15.50"; "0.00" -> "$0". */
export function formatSigned(value: string | null | undefined): string {
  if (value == null || value === "") return "-";
  const { sign, whole, cents } = split(value);
  const tail = cents === "" || /^0+$/.test(cents) ? "" : `.${cents}`;
  const isZero = /^0+$/.test(whole) && tail === "";
  const mark = isZero ? "" : sign === "-" ? "-" : "+";
  return `${mark}$${group(whole)}${tail}`;
}

/** Cents as a BigInt, for exact ordering without floats. */
export function toCents(value: string | null | undefined): bigint {
  if (value == null || value === "") return BigInt(0);
  const { sign, whole, cents } = split(value);
  const total = BigInt(whole + cents);
  return sign === "-" ? -total : total;
}

export function compareMoney(
  left: string | null | undefined,
  right: string | null | undefined,
): number {
  const a = toCents(left);
  const b = toCents(right);
  return a === b ? 0 : a < b ? -1 : 1;
}

export function isNegative(value: string | null | undefined): boolean {
  return value != null && value.trim().startsWith("-");
}
