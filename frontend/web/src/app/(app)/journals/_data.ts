/**
 * The journals screen's vocabulary - and nothing else.
 *
 * The product holds no content of its own: every entry, account and amount on
 * this screen comes from `GET /api/journals`, which answers with the entries a
 * close actually posted for a month. So this file carries only what the
 * *renderer* needs to draw an entry it has never seen: the payload's shape,
 * the column labels, and the two formatters that turn the backend's enum
 * tokens and ISO stamps into something readable.
 */

/** One side of one entry. `side` is the backend's own `"Dr"` / `"Cr"`. */
export type JournalLine = {
  side: string;
  account: string;
  /** Already formatted by the backend, e.g. a currency string. */
  amount: string;
};

/** One balanced entry: whose it is, why it exists, and what it books. */
export type JournalEntry = {
  /** `"<period>/<case_key>"` - the `?case=` value every close screen reads. */
  case_id: string;
  case_key: string;
  period: string;
  vendor: string;
  vendor_id: string;
  /** An enum token, e.g. the accrual/true-up distinction. */
  kind: string;
  /** ISO-8601 stamp of when the entry was posted. */
  at: string;
  /** An enum token naming what the amount was derived from. */
  basis: string;
  lines: JournalLine[];
};

/**
 * `GET /api/journals[?period=YYYY-MM]`.
 *
 * `accounts` is the chart of accounts the API says it uses for display, and
 * `note` is its own caveat about that. Both are optional: the screen renders
 * whatever arrives and never assumes either is there.
 */
export type JournalsData = {
  journals?: JournalEntry[];
  accounts?: Record<string, string>;
  note?: string;
};

/** A month the backend answered for with no entries is "nothing to show". */
export function journalsIsEmpty(data: JournalsData): boolean {
  return !Array.isArray(data.journals) || data.journals.length === 0;
}

export const COLUMNS: readonly string[] = [
  "VENDOR",
  "CASE",
  "KIND",
  "BASIS",
  "POSTED",
  "ENTRY",
];

/**
 * An enum token as a sentence.
 *
 * The backend names kinds and bases in screaming snake case. Rather than a
 * lookup table - which would be this app inventing a vocabulary, and would
 * render a token it had not been taught as a blank - the token is lowercased
 * and its first letter raised, so an unseen one still reads.
 */
/**
 * Accounting acronyms that must stay shouted.
 *
 * The generic rule below lowercases a token before capitalising it, which
 * turns `PO_BUDGET` into "Po budget" - a word nobody writes. Keeping a short,
 * explicit list of the acronyms this domain actually uses is more honest than
 * a clever rule: a length heuristic would read `TRUE_UP` as "True UP".
 */
const ACRONYMS = new Set(["PO", "GL", "AP", "GR", "ID", "VAT"]);

/** `PO_BUDGET` -> "PO budget", `TRUE_UP` -> "True up". */
export function tokenLabel(token: string): string {
  const parts = token.trim().split("_").filter(Boolean);
  if (parts.length === 0) return token;
  return parts
    .map((part, i) => {
      const upper = part.toUpperCase();
      if (ACRONYMS.has(upper)) return upper;
      const lower = part.toLowerCase();
      return i === 0 ? lower.charAt(0).toUpperCase() + lower.slice(1) : lower;
    })
    .join(" ");
}

/* Fixed locale and time zone, so the server's render and the client's
   hydration produce the same characters. The backend stamps in UTC. */
const DATE_FORMAT = new Intl.DateTimeFormat("en-US", {
  timeZone: "UTC",
  month: "short",
  day: "numeric",
  year: "numeric",
});

const TIME_FORMAT = new Intl.DateTimeFormat("en-US", {
  timeZone: "UTC",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

/**
 * An ISO stamp split into the two lines the tables in this product use.
 *
 * Anything unparseable comes back as itself with no time line: a stamp the
 * app cannot read is still the backend's answer, and showing it raw is more
 * honest than showing nothing.
 */
export function stamp(at: string): { date: string; time: string | null } {
  const value = new Date(at);
  if (Number.isNaN(value.getTime())) return { date: at, time: null };
  return {
    date: DATE_FORMAT.format(value),
    time: `${TIME_FORMAT.format(value)} UTC`,
  };
}

/** A debit reads as the weightier of the two sides, as in a paper journal. */
export function isDebit(side: string): boolean {
  return side.trim().toLowerCase().startsWith("d");
}
