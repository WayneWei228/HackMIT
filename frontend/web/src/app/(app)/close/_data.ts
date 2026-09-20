/**
 * Close case screen config: glyph names, the rail's labels and geometry. What the
 * agent found - files, figures, names - comes from the backend (see `_view.ts`).
 * All data is synthetic and every upstream system is simulated.
 */

export type SourceGlyph = "page" | "mail" | "chat";

export type TabGlyph =
  | "sources"
  | "document"
  | "spreadsheet"
  | "memo"
  | "record"
  | "ledger";

export const AGENT_NAME = "Ingestion agent";

export const HANDOFF_FROM = "Ingestion";
export const HANDOFF_TO = "Evidence";
export const CTA_IDLE_LABEL = "Continue to Evidence";

/* -------------------------------------------------------------------------- */
/* Rail geometry                                                               */
/* -------------------------------------------------------------------------- */

export const RAIL_DEFAULT_WIDTH = 330;
export const RAIL_MIN_WIDTH = 288;
export const RAIL_MAX_WIDTH = 620;
