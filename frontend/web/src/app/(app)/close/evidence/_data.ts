/**
 * Evidence screen config: the zoom ladder and the rail labels. The documents and the
 * facts come from the backend (see `_view.ts`). All of it is synthetic - every
 * upstream system is simulated.
 */

export const ZOOMS = ["100%", "125%", "75%"] as const;
export type Zoom = (typeof ZOOMS)[number];

export const ZOOM_SCALES: Record<Zoom, number> = {
  "100%": 1,
  "125%": 1.25,
  "75%": 0.75,
};

/* -------------------------------------------------------------------------- */
/* Execution rail                                                              */
/* -------------------------------------------------------------------------- */

export const RAIL = {
  eyebrow: "LIVE EXECUTION",
  running: "Running",
  factsLabel: "EXTRACTED FACTS",
  handoffLabel: "NEXT HANDOFF",
  handoffFrom: "Evidence",
  handoffTo: "Obligation",
  ctaIdle: "Continue to Obligation",
  ctaAuto: "Opening Obligation...",
} as const;

export const AGENT_LABEL = "Evidence agent";
