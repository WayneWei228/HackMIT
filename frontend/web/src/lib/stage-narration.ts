"use client";

import { useMemo } from "react";

import type { LogEntry } from "./api-types";
import { useCaseRun } from "./case-runner";
import { useCaseId } from "./case-context";
import { useCaseTrail } from "./case-trail";
import { useStageFlow } from "./stage-flow";
import type { StageKey } from "./case-store";
import { agentLabel, agentsOn, screenOfAgent } from "./trail";

export type Narration = {
  phase: "loading" | "error" | "unavailable" | "empty" | "ready";
  /** The recorded steps of this stage's agents, oldest first. */
  entries: LogEntry[];
  /** A short line for the status bar: the newest recorded step, or an honest state. */
  text: string;
  /** True while a backend call for this stage is in flight. */
  running: boolean;
};

/**
 * What this stage's agents did, read from the run log and nothing else. The bar
 * text is the title of the newest recorded entry; when there is no log to read
 * it says so instead of narrating from a script.
 */
export function useStageNarration(screen: StageKey): Narration {
  const id = useCaseId();
  const trail = useCaseTrail();
  const run = useCaseRun(id);
  const running = run.active && run.stage === screen && run.callStartedAt !== null;
  const flow = useStageFlow(screen);

  const entries = useMemo(() => {
    const mine = new Set(agentsOn(screen));
    return (trail.log?.entries ?? [])
      .filter((entry) => mine.has(entry.agent) && entry.kind !== "VERIFICATION" && !entry.superseded)
      .sort((a, b) => a.seq - b.seq);
  }, [trail.log, screen]);

  if (running) {
    const agent = run.agent && screenOfAgent(run.agent) === screen ? agentLabel(run.agent) : null;
    return { phase: "ready", entries, running, text: `${agent ?? "Agent"} running` };
  }
  if (flow.phase === "waiting") {
    return { phase: "empty", entries, running, text: `Waiting for the ${flow.waitingFor ?? "previous agent"}` };
  }
  if (flow.phase === "starting") {
    return { phase: "empty", entries, running, text: "Starting" };
  }
  if (flow.phase === "failed") {
    return { phase: "error", entries, running, text: flow.error ?? "The last call failed" };
  }
  if (flow.phase === "rest") {
    return { phase: "empty", entries, running, text: "Nothing more runs here: the case is waiting on someone else" };
  }
  if (trail.status === "loading") {
    return { phase: "loading", entries, running, text: "Reading the run log" };
  }
  if (trail.status === "error") {
    return { phase: "error", entries, running, text: `Run log not readable: ${trail.error ?? "unknown error"}` };
  }
  if (trail.unavailable) {
    return { phase: "unavailable", entries, running, text: "The backend has no run log endpoint yet" };
  }
  const latest = entries[entries.length - 1];
  if (!latest) {
    return { phase: "empty", entries, running, text: "No recorded steps for this stage" };
  }
  return { phase: "ready", entries, running, text: latest.title };
}
