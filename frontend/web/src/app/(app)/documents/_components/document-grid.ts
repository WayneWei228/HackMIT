/**
 * The seven-column track shared by the document table's head and its rows.
 *
 * A document is one flat record - no nested lines - so the row centres, and
 * the two identifier columns (the document and its file) take the slack.
 */
export const DOCUMENT_GRID =
  "grid grid-cols-[minmax(180px,1.2fr)_138px_minmax(110px,0.8fr)_112px_112px_116px_minmax(120px,0.9fr)] items-center gap-x-[14px]";
