import { routes } from "@/lib/routes";

/**
 * The Obligation screen's layout constants. What the agents found - facts,
 * checks, the conclusion - comes from the backend (see `_view.ts`). All data is
 * synthetic and every upstream system is simulated.
 */

export const RAIL_WIDTH = { initial: 330, min: 288, max: 620 } as const;

export const handoff = {
  from: "Obligation",
  to: "Estimation",
  href: routes.estimation,
  idleLabel: "Hand off to Estimation",
} as const;
