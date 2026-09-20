/**
 * The documents screen's vocabulary - and nothing else.
 *
 * Every document on this screen comes from `GET /api/documents`: the files a
 * close read for a month, what was extracted from each, and whether the
 * extraction came out clean. The screen holds no documents of its own.
 */

/**
 * The record extracted from a document.
 *
 * Its shape is the document type's, so it varies; the one field this screen
 * reads is the vendor's name, which the list itself only carries as an id.
 */
export type DocumentRecord = {
  vendor_name?: string | null;
  [field: string]: unknown;
};

export type DocumentEntry = {
  doc_id: string;
  /** An enum token, e.g. the invoice/purchase-order distinction. */
  doc_type: string;
  /** `"OK"` when the extraction came out clean; anything else is a flag. */
  quality: string;
  period: string;
  /** The date this document became knowable - `"YYYY-MM-DD"`. */
  known_from: string;
  file_name: string;
  applied_to?: string | null;
  vendor_id?: string | null;
  po_line_id?: string | null;
  record?: DocumentRecord | null;
  /** Why the quality is what it is, when the backend says. */
  reasons?: string[] | null;
};

/** `GET /api/documents[?period=YYYY-MM]`. */
export type DocumentsData = { documents?: DocumentEntry[] };

/** A month the backend answered for with no documents is "nothing to show". */
export function documentsIsEmpty(data: DocumentsData): boolean {
  return !Array.isArray(data.documents) || data.documents.length === 0;
}

export const COLUMNS: readonly string[] = [
  "DOCUMENT",
  "TYPE",
  "VENDOR",
  "PERIOD",
  "KNOWN FROM",
  "QUALITY",
  "FILE",
];

/**
 * Who the document is from.
 *
 * The list carries a vendor id; the extracted record usually carries the name
 * the vendor writes on its own paperwork, which is the one worth reading. A
 * document that names neither - a goods receipt, say - gets neither.
 */
export function vendorOf(doc: DocumentEntry): string | null {
  const name = doc.record?.vendor_name;
  if (typeof name === "string" && name.trim()) return name.trim();
  return doc.vendor_id?.trim() || null;
}

/** Whether the extraction came out clean. */
export function isClean(quality: string): boolean {
  return quality.trim().toUpperCase() === "OK";
}

/**
 * An enum token as a sentence: `"PURCHASE_ORDER"` reads as one word raised.
 *
 * No lookup table, so a document type this app has never been taught still
 * renders as itself rather than as a blank.
 */
export function tokenLabel(token: string): string {
  const words = token.replace(/_/g, " ").trim().toLowerCase();
  if (!words) return token;
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/* Fixed locale and time zone, so the server's render and the client's
   hydration produce the same characters. */
const DATE_FORMAT = new Intl.DateTimeFormat("en-US", {
  timeZone: "UTC",
  month: "short",
  day: "numeric",
  year: "numeric",
});

/** A `"YYYY-MM-DD"` date, read. Anything unparseable comes back as itself. */
export function dayLabel(day: string): string {
  const value = new Date(day);
  if (Number.isNaN(value.getTime())) return day;
  return DATE_FORMAT.format(value);
}
