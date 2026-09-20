/**
 * Canonical routes. The comps navigate between static files; this is the same
 * graph expressed as app-router paths.
 *
 * The close run is a chain: case -> evidence -> obligation -> estimation ->
 * verification, each agent handing off to the next.
 */
export const routes = {
  home: "/",
  cases: "/cases",
  vendors: "/vendors",
  learning: "/learning",
  closeCase: "/close",
  evidence: "/close/evidence",
  obligation: "/close/obligation",
  estimation: "/close/estimation",
  verification: "/close/verification",
} as const;

/** Order of the agent chain, used for handoff and for the stepper. */
export const agentChain = [
  { id: "evidence", label: "Evidence", href: routes.evidence },
  { id: "obligation", label: "Obligation", href: routes.obligation },
  { id: "estimation", label: "Estimation", href: routes.estimation },
  { id: "verification", label: "Verification", href: routes.verification },
] as const;
