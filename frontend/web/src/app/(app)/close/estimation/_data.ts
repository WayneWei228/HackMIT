import { routes } from "@/lib/routes";

/**
 * The Estimation screen's fixed pieces: node state names and the handoff link.
 * Every step, sub-check, figure and sentence on the screen is built from the
 * workpaper the backend returned (see `_view.ts`). All data is synthetic and
 * every upstream system is simulated.
 */

export type NodeState = "pending" | "active" | "done";

export const HANDOFF = {
  from: "Estimation",
  to: "Verification",
  href: routes.verification,
} as const;
