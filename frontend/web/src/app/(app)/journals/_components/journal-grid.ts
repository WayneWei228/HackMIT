/**
 * The six-column track shared by the journal table's head and its rows.
 *
 * The last column holds the entry's Dr/Cr lines stacked, so it is the widest
 * and the whole row aligns to the top rather than to the middle - a two-line
 * entry and a five-line one have to start on the same baseline.
 */
export const JOURNAL_GRID =
  "grid grid-cols-[minmax(130px,0.8fr)_132px_104px_150px_104px_minmax(260px,1.6fr)] items-start gap-x-[14px]";
