"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useRouter } from "next/navigation";

import { advanceObligation } from "./api";
import type { FrontStage } from "./api-types";
import { caseData, useCachedHeader } from "./case-data";
import { useCaseRecord, useCaseStoreActions, type StageKey } from "./case-store";
import { STAGES, screenOfAgent, stageDone, stageLabelOf } from "./trail";

/** A short beat between stages so a viewer can follow. It never reveals anything early. */
const PAUSE_MS = 700;

export type RunState = {
  /** A stage call is in flight or the next one is about to start. */
  active: boolean;
  /** The stage whose agents are running. */
  stage: StageKey | null;
  /** The run-log name of the agent running, when the backend said so. */
  agent: string | null;
  /** `performance.now()` when the in-flight call began. */
  callStartedAt: number | null;
  /** Waiting behind an earlier case in Start all. */
  queued: boolean;
  error: string | null;
};

const IDLE: RunState = {
  active: false,
  stage: null,
  agent: null,
  callStartedAt: null,
  queued: false,
  error: null,
};

export type RunRequest = {
  obligationId: string;
  /** Stages the backend already reports as completed, so a run resumes and never replays. */
  completed: readonly FrontStage[];
  agent?: string | null;
  /** Stop once this stage is complete. Without it the run goes straight through to a resting state. */
  until?: StageKey;
  /** The reader is watching: each stage this run completes plays its reveal once. */
  reveal?: boolean;
};

type Runner = {
  runs: Record<string, RunState>;
  /** Run these cases stage by stage, one call at a time, one case after another. */
  start: (requests: readonly RunRequest[]) => void;
  /** Stop every run (a reset), leaving the backend as it is. */
  cancelAll: () => void;
};

const RunnerContext = createContext<Runner | null>(null);

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

function nextStage(completed: readonly FrontStage[]): StageKey | null {
  return STAGES.find((stage) => !completed.includes(stage.label))?.key ?? null;
}

/**
 * Mounted once at the (app) layout so an in-flight run keeps going while the
 * reader moves between screens. It makes one real backend call per stage and
 * renders nothing itself: every screen shows only what a call has returned.
 */
export function CaseRunnerProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const store = useCaseStoreActions();
  const [runs, setRuns] = useState<Record<string, RunState>>({});
  const generation = useRef(0);
  const busy = useRef(new Set<string>());

  const patch = useCallback((id: string, change: Partial<RunState>) => {
    setRuns((current) => ({ ...current, [id]: { ...(current[id] ?? IDLE), ...change } }));
  }, []);

  const drive = useCallback(
    async (request: RunRequest, gen: number) => {
      const id = request.obligationId;
      let completed = request.completed;
      let agent = request.agent ?? null;
      const target = request.until ? stageLabelOf(request.until) : null;
      while (gen === generation.current) {
        if (target !== null && completed.includes(target as FrontStage)) {
          patch(id, { active: false, stage: null, agent: null, callStartedAt: null });
          return;
        }
        /* The screen a viewer is waiting on is the first one not yet complete, whichever agent runs. */
        const stage = nextStage(completed);
        patch(id, { active: true, queued: false, stage, agent, callStartedAt: performance.now() });
        let result;
        try {
          result = await advanceObligation(id);
        } catch (caught) {
          if (gen === generation.current) {
            patch(id, {
              active: false,
              callStartedAt: null,
              error: caught instanceof Error ? caught.message : String(caught),
            });
          }
          return;
        }
        if (gen !== generation.current) return;
        if (result.stage_run) {
          const ran = screenOfAgent(result.stage_run.agent) ?? stage;
          if (ran) store.addDuration(id, ran, result.stage_run.duration_ms);
        }
        const before = completed;
        completed = result.case.header.stages_completed ?? completed;
        agent = result.case.header.current_agent ?? null;
        if (request.reveal) {
          for (const finished of STAGES) {
            if (completed.includes(finished.label) && !before.includes(finished.label)) {
              store.setUi(id, `reveal.${finished.key}`, true);
            }
          }
        }
        /* Evidence reads one document per call: each batch of facts is revealed as it arrives. */
        if (request.reveal && result.stage_run?.partial) store.setUi(id, "reveal.evidence", true);
        /* The screens read this cache, so each one fills in the moment its call returns. */
        caseData.putDetail(id, result.case);
        void caseData.refreshClose();
        router.refresh();
        if (result.done || (target !== null && completed.includes(target as FrontStage))) {
          patch(id, { active: false, stage: null, agent: null, callStartedAt: null });
          return;
        }
        /* Between calls the row already names the agent that runs next. */
        patch(id, { callStartedAt: null, agent, stage: nextStage(completed) });
        await sleep(PAUSE_MS);
      }
    },
    [patch, router, store],
  );

  const start = useCallback(
    (requests: readonly RunRequest[]) => {
      const gen = generation.current;
      const fresh = requests.filter((request) => !busy.current.has(request.obligationId));
      fresh.forEach((request) => {
        busy.current.add(request.obligationId);
        patch(request.obligationId, { ...IDLE, queued: true });
      });
      void (async () => {
        for (const request of fresh) {
          if (gen === generation.current) await drive(request, gen);
          busy.current.delete(request.obligationId);
        }
      })();
    },
    [drive, patch],
  );

  const cancelAll = useCallback(() => {
    generation.current += 1;
    busy.current.clear();
    setRuns({});
    caseData.clear();
  }, []);

  const value = useMemo(() => ({ runs, start, cancelAll }), [runs, start, cancelAll]);
  return <RunnerContext value={value}>{children}</RunnerContext>;
}

/** Start and stop runs from a control; the per-case state lives in `useCaseRun`. */
export function useCaseRunner(): Pick<Runner, "start" | "cancelAll"> {
  const { start, cancelAll } = useRunner();
  return { start, cancelAll };
}

export function useRunner(): Runner {
  const runner = useContext(RunnerContext);
  if (!runner) throw new Error("CaseRunnerProvider is missing from the layout.");
  return runner;
}

/** The run state of one case: idle unless the runner is driving it. */
export function useCaseRun(id: string | null): RunState {
  const { runs } = useRunner();
  return (id ? runs[id] : undefined) ?? IDLE;
}

/** "187ms" under a second, "1.2s" under a minute, "m:ss" beyond it, "-" when nothing was measured. */
export function formatDuration(ms: number | null): string {
  if (ms === null) return "-";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  const seconds = Math.round(ms / 1000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

/**
 * The time a stage took: the measured `duration_ms` of its agent calls once it
 * is complete (frozen, never restarting), counting up live only while its call
 * is in flight, and nothing at all otherwise.
 */
export function useStageClock(id: string | null, stage: StageKey): number | null {
  const { record } = useCaseRecord(id);
  const run = useCaseRun(id);
  const header = useCachedHeader(id);
  const complete = header ? stageDone(header, stage) : false;
  const recorded = record?.durations[stage] ?? null;
  const live = run.active && run.stage === stage && run.callStartedAt !== null && !complete;

  const [now, setNow] = useState(0);
  useEffect(() => {
    if (!live) return;
    const timer = setInterval(() => setNow(performance.now()), 250);
    return () => clearInterval(timer);
  }, [live]);

  if (complete) return recorded;
  if (live && run.callStartedAt !== null) {
    return (recorded ?? 0) + Math.max(0, (now || run.callStartedAt) - run.callStartedAt);
  }
  return recorded;
}
