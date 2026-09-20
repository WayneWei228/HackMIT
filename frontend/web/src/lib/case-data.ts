"use client";

import { useEffect, useSyncExternalStore } from "react";

import { getClose, getObligation } from "./api";
import type { CloseView, ObligationDetail } from "./api-types";

/**
 * What the browser knows about the close, kept between screens so a stage screen
 * can draw its real layout the moment it opens instead of waiting on the server.
 * The backend stays the source of truth: every advance and every read replaces
 * what is held here, and a reset clears it.
 */
type State = {
  close: CloseView | null;
  details: Record<string, ObligationDetail>;
  /** The last read that failed, by case (or "close"), so a screen can say so. */
  errors: Record<string, Error>;
};

let state: State = { close: null, details: {}, errors: {} };
const listeners = new Set<() => void>();
const inflight = new Map<string, Promise<void>>();

function commit(next: State) {
  state = next;
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

const snapshot = () => state;

function once(key: string, read: () => Promise<void>): Promise<void> {
  const running = inflight.get(key);
  if (running) return running;
  const started = read().finally(() => inflight.delete(key));
  inflight.set(key, started);
  return started;
}

function fail(key: string, error: unknown) {
  const cause = error instanceof Error ? error : new Error(String(error));
  commit({ ...state, errors: { ...state.errors, [key]: cause } });
}

function without(errors: Record<string, Error>, key: string) {
  if (!(key in errors)) return errors;
  return Object.fromEntries(Object.entries(errors).filter(([name]) => name !== key));
}

export const caseData = {
  /** Replace one case's detail, for example with what an advance call just returned. */
  putDetail(id: string, detail: ObligationDetail) {
    commit({
      ...state,
      details: { ...state.details, [id]: detail },
      errors: without(state.errors, id),
    });
  },
  putClose(close: CloseView) {
    commit({ ...state, close, errors: without(state.errors, "close") });
  },
  /** Read the close list again. */
  refreshClose(): Promise<void> {
    return once("close", async () => {
      try {
        caseData.putClose(await getClose());
      } catch (error) {
        fail("close", error);
      }
    });
  },
  /** Read one case again. */
  refreshDetail(id: string): Promise<void> {
    return once(id, async () => {
      try {
        caseData.putDetail(id, await getObligation(id));
      } catch (error) {
        fail(id, error);
      }
    });
  },
  /** Read the close and every case the browser holds again, after something changed the backend. */
  async refreshAll(): Promise<void> {
    await Promise.all([
      caseData.refreshClose(),
      ...Object.keys(state.details).map((id) => caseData.refreshDetail(id)),
    ]);
  },
  /** Warm the cache for a case, waiting no longer than `maxMs` for the backend. */
  async prefetch(id: string, maxMs = 300): Promise<void> {
    const read = Promise.all([caseData.refreshDetail(id), caseData.refreshClose()]);
    await Promise.race([read, new Promise((resolve) => setTimeout(resolve, maxMs))]);
  },
  /** Forget everything (a reset), so nothing from the old run can show. */
  clear() {
    inflight.clear();
    commit({ close: null, details: {}, errors: {} });
  },
};

/** The close and one case, read from the cache and kept fresh; `id` null means the close's first case. */
export function useCaseData(requested: string | null): {
  close: CloseView | null;
  id: string | null;
  detail: ObligationDetail | null;
  error: Error | null;
} {
  const current = useSyncExternalStore(subscribe, snapshot, snapshot);
  const id = requested ?? current.close?.cases[0]?.obligation_id ?? null;

  useEffect(() => {
    if (!current.close) void caseData.refreshClose();
  }, [current.close]);

  useEffect(() => {
    if (id) void caseData.refreshDetail(id);
  }, [id]);

  return {
    close: current.close,
    id,
    detail: id ? (current.details[id] ?? null) : null,
    error: (id && current.errors[id]) || current.errors.close || null,
  };
}

/** The header of a case the browser already holds, without asking the backend for anything. */
export function useCachedHeader(id: string | null): ObligationDetail["header"] | null {
  const current = useSyncExternalStore(subscribe, snapshot, snapshot);
  return id ? (current.details[id]?.header ?? null) : null;
}

/** The close as the browser last read it, kept fresh; `initial` is what the server rendered. */
export function useClose(initial: CloseView | null = null): CloseView | null {
  const current = useSyncExternalStore(subscribe, snapshot, snapshot);
  useEffect(() => {
    if (initial) caseData.putClose(initial);
  }, [initial]);
  useEffect(() => {
    if (!current.close && !initial) void caseData.refreshClose();
  }, [current.close, initial]);
  return current.close ?? initial;
}
