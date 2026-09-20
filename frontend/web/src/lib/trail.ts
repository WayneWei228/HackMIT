import type { FrontStage, GateVerdict, Handoff, LogEntry } from "./api-types";
import type { StageKey } from "./case-store";

/** The five stages of a close, in the order the agents run them. */
export const STAGES: readonly { key: StageKey; label: FrontStage }[] = [
  { key: "ingestion", label: "Ingestion" },
  { key: "evidence", label: "Evidence" },
  { key: "obligation", label: "Obligation" },
  { key: "estimation", label: "Estimation" },
  { key: "verification", label: "Verification" },
];

export function stageLabelOf(key: StageKey): FrontStage {
  return STAGES.find((stage) => stage.key === key)?.label ?? "Ingestion";
}

/** Whether every agent of this stage has run, according to the backend. */
export function stageDone(
  header: { started: boolean; stages_completed?: readonly FrontStage[] },
  key: StageKey,
): boolean {
  const completed = header.stages_completed;
  if (completed) return completed.includes(stageLabelOf(key));
  return header.started;
}

/** The run-log name each backend agent writes under, as the reader should see it. */
const AGENT_LABELS: Record<string, string> = {
  detection: "Detection agent",
  invoice_lookup: "Invoice lookup agent",
  ingestion: "Ingestion agent",
  evidence: "Evidence agent",
  classification: "Obligation agent",
  estimation: "Estimation agent",
  policy: "Policy enforcer",
  reviewer: "Reviewer agent",
  controller_workspace: "Controller workspace",
  journal_entry_service: "Journal entry service",
  outreach: "Outreach agent",
  reconciliation: "Reconciliation agent",
  learning: "Learning agent",
  auditor: "Auditor agent",
  verifier: "Formal verifier",
  orchestrator: "Orchestrator",
};

export function agentLabel(agent: string): string {
  const known = AGENT_LABELS[agent];
  if (known) return known;
  const words = agent.replace(/_/g, " ").trim();
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : "Agent";
}

/** Which stage screen each agent's work belongs to. */
const SCREEN_AGENTS: Record<StageKey, readonly string[]> = {
  ingestion: ["ingestion"],
  evidence: ["evidence"],
  obligation: ["detection", "invoice_lookup", "classification"],
  estimation: ["estimation"],
  verification: [
    "policy",
    "reviewer",
    "journal_entry_service",
    "controller_workspace",
    "outreach",
    "reconciliation",
    "learning",
    "auditor",
  ],
};

export function agentsOn(screen: StageKey): readonly string[] {
  return SCREEN_AGENTS[screen];
}

/** The stage a run-log agent belongs to, or null for cross-cutting agents like the verifier. */
export function screenOfAgent(agent: string | null | undefined): StageKey | null {
  if (!agent) return null;
  for (const stage of STAGES) if (SCREEN_AGENTS[stage.key].includes(agent)) return stage.key;
  return null;
}

/** The screen that follows this one in the chain, or null after Verification. */
const NEXT_SCREEN: Record<StageKey, StageKey | null> = {
  ingestion: "evidence",
  evidence: "obligation",
  obligation: "estimation",
  estimation: "verification",
  verification: null,
};

/** The newest thing this screen's agents did, for the bar's narration. */
export function latestFor(screen: StageKey, entries: readonly LogEntry[]): LogEntry | null {
  const mine = new Set(agentsOn(screen));
  let latest: LogEntry | null = null;
  for (const entry of entries) {
    if (entry.kind === "VERIFICATION" || !mine.has(entry.agent)) continue;
    if (!latest || entry.seq > latest.seq) latest = entry;
  }
  return latest;
}

/** How many formal-verification controls passed across the whole trail. */
export function verificationTotals(entries: readonly LogEntry[]): { passed: number; total: number } {
  let passed = 0;
  let total = 0;
  for (const entry of entries) {
    if (!entry.verification) continue;
    passed += entry.verification.passed;
    total += entry.verification.total;
  }
  return { passed, total };
}

/** The handoff that leaves this screen's agents for the next screen's, if it has happened. */
export function outgoingHandoff(screen: StageKey, handoffs: readonly Handoff[]): Handoff | null {
  const mine = new Set(agentsOn(screen));
  const nextScreen = NEXT_SCREEN[screen];
  const theirs = new Set(nextScreen ? agentsOn(nextScreen) : []);
  let found: Handoff | null = null;
  for (const handoff of handoffs) {
    if (!mine.has(handoff.from_agent)) continue;
    if (nextScreen && !theirs.has(handoff.to_agent)) continue;
    if (!found || handoff.seq > found.seq) found = handoff;
  }
  return found;
}

export const VERDICT_STYLES: Record<
  GateVerdict,
  { chip: string; rail: string; dot: string; label: string }
> = {
  PERMIT: {
    chip: "bg-accent-soft-2 text-accent-press",
    rail: "bg-[#2E8047]",
    dot: "#2E8047",
    label: "PERMIT",
  },
  BLOCK: {
    chip: "bg-[#F6E4DF] text-[#A4452F]",
    rail: "bg-[#C2543D]",
    dot: "#C2543D",
    label: "BLOCK",
  },
  REVIEW: {
    chip: "bg-[#F6ECD3] text-[#8A6516]",
    rail: "bg-[#D6A43C]",
    dot: "#D6A43C",
    label: "REVIEW",
  },
  OUTREACH: {
    chip: "bg-[#E4EBF3] text-[#3F5A7C]",
    rail: "bg-[#7C93B0]",
    dot: "#7C93B0",
    label: "OUTREACH",
  },
};

/** A stage edge written for reading: "SEARCHING_AP" -> "Searching AP". */
export function stageLabel(stage: string | null): string {
  if (!stage) return "-";
  const words = stage.toLowerCase().replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}
