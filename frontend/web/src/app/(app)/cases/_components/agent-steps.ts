import type { RunStatus } from "@/lib/use-run-controls";

/** Where one agent of the chain has got to. */
export type AgentStepState = "pending" | "running" | "done";

export type AgentStep = {
  /** The backend's snake id for the worker, e.g. `invoice_lookup`. */
  id: string;
  /** How the product names it, e.g. `Invoice Lookup`. */
  label: string;
  state: AgentStepState;
  /** The newest line this agent emitted, if it emitted one. */
  message: string | null;
};

/**
 * The seven agents, in the order the runner walks them.
 *
 * The ids are the backend's `progress[].worker` values, which do not all match
 * the product's names for the agents: `classifier` is Classification, and the
 * rest differ only in punctuation. `runner` is not an agent - it is the thing
 * driving them - so it is absent here and ignored below.
 */
export const CHAIN_AGENTS: readonly { id: string; label: string }[] = [
  { id: "evidence", label: "Evidence" },
  { id: "detection", label: "Detection" },
  { id: "invoice_lookup", label: "Invoice Lookup" },
  { id: "classifier", label: "Classification" },
  { id: "estimation", label: "Estimation" },
  { id: "outreach", label: "Outreach" },
  { id: "settlement", label: "Settlement" },
];

/** Spellings of the same worker we are willing to accept from the API. */
const ALIASES: Record<string, string> = {
  classification: "classifier",
  classify: "classifier",
  invoice: "invoice_lookup",
  invoicelookup: "invoice_lookup",
  settle: "settlement",
  evidence_worker: "evidence",
};

function normalise(worker: unknown): string | null {
  if (typeof worker !== "string") return null;
  const key = worker.trim().toLowerCase().replace(/[\s-]+/g, "_");
  if (!key) return null;
  return ALIASES[key] ?? key;
}

/** Where a worker sits in the chain, or `null` for `runner` and the unknown. */
function agentIndex(worker: unknown): number | null {
  const key = normalise(worker);
  if (key === null) return null;
  const index = CHAIN_AGENTS.findIndex((agent) => agent.id === key);
  return index === -1 ? null : index;
}

function text(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

/**
 * The shape the API is growing: `status.agents`, already in chain terms.
 *
 * `RunStatus` does not declare it yet, so it is read off the object rather
 * than off the type, and every field is treated as unknown until proven
 * otherwise. `null` means "the API did not say" - not "nothing is running" -
 * so the caller falls back to the progress lines.
 */
function stepsFromAgents(status: RunStatus | null): AgentStep[] | null {
  const raw = (status as { agents?: unknown } | null)?.agents;
  if (!Array.isArray(raw) || raw.length === 0) return null;

  const seen = new Map<number, { state: AgentStepState; message: string | null }>();
  for (const entry of raw) {
    if (!entry || typeof entry !== "object") continue;
    const row = entry as { agent?: unknown; state?: unknown; last_message?: unknown };
    const index = agentIndex(row.agent);
    if (index === null) continue; // an agent we do not draw
    const state =
      row.state === "running" || row.state === "done" || row.state === "pending"
        ? row.state
        : "pending";
    seen.set(index, { state, message: text(row.last_message) });
  }
  if (seen.size === 0) return null;

  return CHAIN_AGENTS.map((agent, index) => {
    const found = seen.get(index);
    return {
      id: agent.id,
      label: agent.label,
      state: found?.state ?? "pending",
      message: found?.message ?? null,
    };
  });
}

/**
 * The shape the API has today: a flat list of `{worker, message}` lines.
 *
 * The chain is strictly ordered, so the newest line from a known worker says
 * where the run is: that agent is running, everything before it has finished,
 * everything after it is still waiting. `runner` lines carry no position - the
 * runner is not one of the seven - but they are perfectly good log lines, so
 * they still count towards the latest message.
 */
function stepsFromProgress(status: RunStatus | null): AgentStep[] {
  const progress = Array.isArray(status?.progress) ? status.progress : [];

  let active = -1;
  let latest: string | null = null;
  const messages = new Map<number, string>();

  for (const entry of progress) {
    if (!entry || typeof entry !== "object") continue;
    const message = text(entry.message);
    if (message) latest = message;
    const index = agentIndex(entry.worker);
    if (index === null) continue;
    active = index;
    if (message) messages.set(index, message);
  }

  return CHAIN_AGENTS.map((agent, index) => ({
    id: agent.id,
    label: agent.label,
    state:
      active < 0 || index > active
        ? "pending"
        : index === active
          ? "running"
          : "done",
    /* The active agent shows the newest line of the whole run - including the
       runner's - because that is what the chain is doing right now. */
    message:
      index === active
        ? (latest ?? messages.get(index) ?? null)
        : (messages.get(index) ?? null),
  }));
}

/**
 * The seven agents and where the run has got to, however the API says it.
 *
 * Always seven steps, in chain order: a run that has emitted nothing yet is
 * seven pending steps rather than an empty strip that pops into existence.
 */
export function agentSteps(status: RunStatus | null): AgentStep[] {
  return stepsFromAgents(status) ?? stepsFromProgress(status);
}

/** The index of the agent currently running, or -1 when none is. */
export function activeStep(steps: readonly AgentStep[]): number {
  return steps.findIndex((step) => step.state === "running");
}

/**
 * Whether the chain has actually started.
 *
 * A job that is not the seven agents - a reset, or a run-all with nothing
 * left to do - never lights a step, and drawing seven grey ones for it would
 * claim a chain that is not running. "Started" rather than "running" so the
 * strip keeps the finished chain on screen for the last poll of a job instead
 * of blinking it away the moment the seventh agent goes `done`.
 */
export function chainStarted(steps: readonly AgentStep[]): boolean {
  return steps.some((step) => step.state !== "pending");
}
