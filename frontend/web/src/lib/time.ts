const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export type Stamp = {
  /** "Dec 31, 2026" */
  date: string;
  /** "11:59 PM" */
  time: string;
  /** Sortable milliseconds since the epoch. */
  ts: number;
};

/** Formats a simulation timestamp in UTC so the server and the browser agree. */
export function formatStamp(iso: string): Stamp {
  const moment = new Date(iso);
  const hours = moment.getUTCHours();
  const minutes = String(moment.getUTCMinutes()).padStart(2, "0");
  return {
    date: `${MONTHS[moment.getUTCMonth()]} ${moment.getUTCDate()}, ${moment.getUTCFullYear()}`,
    time: `${hours % 12 === 0 ? 12 : hours % 12}:${minutes} ${hours < 12 ? "AM" : "PM"}`,
    ts: moment.getTime(),
  };
}

/** "2026-12" -> "December 2026". */
export function periodLabel(period: string): string {
  const [year, month] = period.split("-");
  const names = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
  ];
  return `${names[Number(month) - 1] ?? month} ${year}`;
}
