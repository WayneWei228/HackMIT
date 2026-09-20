/** `$1,200`, `-$5,300`, and with `signed` `+$200`: whole dollars unless there are cents. */
export function usd(value: number, signed = false): string {
  const digits = Number.isInteger(value) ? 0 : 2;
  const body = Math.abs(value).toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  const sign = value < 0 ? "-" : signed && value > 0 ? "+" : "";
  return `${sign}$${body}`;
}
