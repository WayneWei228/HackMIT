"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { getCaseHandoffs, getCaseLog } from "./api";
import type { CaseHandoffs, CaseLog } from "./api-types";

/**
 * The case's recorded trail - its reasoning log and the handoffs between agents
 * - read from the backend and nowhere else. Nothing in the UI narrates an agent
 * from a script: when this cannot load, screens say so plainly.
 */
export type TrailState = {
  status: "loading" | "ready" | "error";
  log: CaseLog | null;
  handoffs: CaseHandoffs | null;
  /** The backend answered 404 for both endpoints: it predates the run log. */
  unavailable: boolean;
  error: string | null;
};

type TrailValue = TrailState & {
  /** Read the trail again, for example after the reader changed the file selection. */
  refresh: () => Promise<void>;
};

const cache = new Map<string, Pick<TrailState, "log" | "handoffs">>();

async function load(id: string): Promise<TrailState> {
  try {
    const [log, handoffs] = await Promise.all([getCaseLog(id), getCaseHandoffs(id)]);
    cache.set(id, { log, handoffs });
    return {
      status: "ready",
      log,
      handoffs,
      unavailable: log === null && handoffs === null,
      error: null,
    };
  } catch (caught) {
    return {
      status: "error",
      log: null,
      handoffs: null,
      unavailable: false,
      error: caught instanceof Error ? caught.message : String(caught),
    };
  }
}

const TrailContext = createContext<TrailValue | null>(null);

/**
 * Loads a case's trail once for every screen part that reads it. `version` is
 * a key that changes when the log or handoff list grew, so a new server render that
 * changed the trail triggers a fresh read.
 */
export function TrailProvider({
  obligationId,
  version,
  children,
}: {
  obligationId: string;
  version?: string | number;
  children: ReactNode;
}) {
  const [state, setState] = useState<TrailState>({
    status: "loading",
    log: null,
    handoffs: null,
    unavailable: false,
    error: null,
  });

  useEffect(() => {
    let live = true;
    const cached = cache.get(obligationId);
    if (cached) {
      /* Show the last read straight away, then replace it with a fresh one. */
      void Promise.resolve().then(() => {
        if (live) {
          setState({
            status: "ready",
            ...cached,
            unavailable: cached.log === null && cached.handoffs === null,
            error: null,
          });
        }
      });
    }
    void load(obligationId).then((next) => {
      if (live) setState(next);
    });
    return () => {
      live = false;
    };
  }, [obligationId, version]);

  const refresh = useCallback(async () => {
    setState(await load(obligationId));
  }, [obligationId]);

  const value = useMemo(() => ({ ...state, refresh }), [state, refresh]);
  return <TrailContext value={value}>{children}</TrailContext>;
}

/** The surrounding case's trail; an empty "loading" trail outside a case screen. */
export function useCaseTrail(): TrailValue {
  const value = useContext(TrailContext);
  if (!value) throw new Error("useCaseTrail needs a TrailProvider (mounted by CaseProvider).");
  return value;
}
