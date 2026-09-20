/**
 * Canonical routes. The comps navigate between static files; this is the same
 * graph expressed as app-router paths.
 *
 * The close run is the backend's agent chain: evidence -> detection ->
 * invoice lookup -> classification -> estimation -> outreach -> settlement.
 * `/close` is the Evidence agent's intake view (the documents it read this
 * month); `/close/evidence` is the same agent's reader.
 */
export const routes = {
  home: "/",
  cases: "/cases",
  journals: "/journals",
  documents: "/documents",
  vendors: "/vendors",
  closeCase: "/close",
  /** One case told in the order it happened. */
  story: "/close/story",
  evidence: "/close/evidence",
  detection: "/close/detection",
  invoiceLookup: "/close/invoice-lookup",
  classification: "/close/classification",
  estimation: "/close/estimation",
  outreach: "/close/outreach",
  settlement: "/close/settlement",
} as const;

/** Order of the agent chain, used for handoff and for the stepper. */
export const agentChain = [
  { id: "evidence", label: "Evidence", href: routes.evidence },
  { id: "detection", label: "Detection", href: routes.detection },
  { id: "invoice-lookup", label: "Invoice Lookup", href: routes.invoiceLookup },
  {
    id: "classification",
    label: "Classification",
    href: routes.classification,
  },
  { id: "estimation", label: "Estimation", href: routes.estimation },
  { id: "outreach", label: "Outreach", href: routes.outreach },
  { id: "settlement", label: "Settlement", href: routes.settlement },
] as const;

export type AgentChainId = (typeof agentChain)[number]["id"];

/**
 * Carry the selected case across a link.
 *
 * Every close screen reads `?case=<period>/<case_key>`; a link that dropped it
 * would silently send the next agent back to the demo dataset, so all internal
 * navigation between close screens goes through here. With no case selected
 * the href is returned untouched and the chain stays on the mock.
 */
export function withCase(href: string, caseParam?: string | null): string {
  if (!caseParam) return href;
  const separator = href.includes("?") ? "&" : "?";
  return `${href}${separator}case=${encodeURIComponent(caseParam)}`;
}

/** Routes the chain retired, and where their work went. */
const RETIRED: Readonly<Record<string, string>> = {
  "/close/obligation": routes.detection,
  "/close/verification": routes.settlement,
  "/close/ingestion": routes.closeCase,
};

const KNOWN: ReadonlySet<string> = new Set(Object.values(routes));

/**
 * An href that arrived from the API, made safe to render.
 *
 * The backend still names a couple of screens by their old route, and a live
 * payload may cite a path this app has never had. A link that 404s is worse
 * than no link, so anything unrecognised comes back `null` and the caller
 * renders plain text instead.
 */
export function safeHref(
  href: string | null | undefined,
  caseParam?: string | null,
): string | null {
  if (!href) return null;
  const [path] = href.split("?");
  const mapped = RETIRED[path] ?? (KNOWN.has(path) ? path : null);
  return mapped ? withCase(mapped, caseParam) : null;
}

/**
 * Carry the selected month across a link.
 *
 * The month is a property of where the reader is, not of the case, so it
 * rides in the URL the same way the case does. On a close screen the case's
 * own period wins, so only the list screens need this.
 */
export function withPeriodParam(
  href: string,
  period?: string | null,
): string {
  if (!period) return href;
  const separator = href.includes("?") ? "&" : "?";
  return `${href}${separator}period=${encodeURIComponent(period)}`;
}

export type ChainStageState = "complete" | "current" | "next" | "pending";

export type ChainStage = {
  /** `"01"` .. `"07"`, the agent's place in the run. */
  number: string;
  name: string;
  /** Null on the screen you are already on. */
  href: string | null;
  state: ChainStageState;
};

/**
 * The close chain as seen from one of its screens.
 *
 * This is navigation, not content: which agents exist and in what order is a
 * property of the product, the same way the sidebar is, so it is derived here
 * rather than served per case. What each agent *found* is content and comes
 * from the API.
 */
export function chainStages(
  currentId: string,
  caseParam?: string | null,
): ChainStage[] {
  const index = agentChain.findIndex((agent) => agent.id === currentId);
  return agentChain.map((agent, i) => {
    const state: ChainStageState =
      i < index
        ? "complete"
        : i === index
          ? "current"
          : i === index + 1
            ? "next"
            : "pending";
    return {
      number: String(i + 1).padStart(2, "0"),
      name: agent.label,
      href: i === index ? null : withCase(agent.href, caseParam),
      state,
    };
  });
}

/** The agent this one hands off to, or null at the end of the chain. */
export function nextAgent(currentId: string) {
  const index = agentChain.findIndex((agent) => agent.id === currentId);
  if (index < 0 || index + 1 >= agentChain.length) return null;
  return agentChain[index + 1];
}

/** The agent's own entry in the chain. */
export function agentOf(currentId: string) {
  return agentChain.find((agent) => agent.id === currentId) ?? null;
}
