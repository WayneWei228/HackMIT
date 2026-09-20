"use client";

import { createContext, useCallback, useContext, useMemo, useSyncExternalStore } from "react";
import type { ReactNode } from "react";

/**
 * What the browser remembers about each case between screens: the measured time
 * each stage took, and the small bits of UI state - open panels, chosen tabs,
 * rail widths - that should still be there when the reader comes back from All
 * cases.
 *
 * The backend is the source of truth for what has run. `reconcile` drops
 * anything the backend no longer agrees with (a reset, a restart, a case that is
 * Pending again), and a reset clears the lot. The store lives in sessionStorage
 * so a reload keeps it.
 */

export type StageKey = "ingestion" | "evidence" | "obligation" | "estimation" | "verification";

type CaseRecord = {
  /** Milliseconds each stage's agents really took, summed over their calls. */
  durations: Partial<Record<StageKey, number>>;
  ui: Record<string, unknown>;
};

type StoreState = { hydrated: boolean; cases: Record<string, CaseRecord> };

const STORAGE_KEY = "trueup.caseStore.v2";
const SERVER_STATE: StoreState = { hydrated: false, cases: {} };

function load(): StoreState {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return { hydrated: true, cases: {} };
    const parsed = JSON.parse(raw) as { cases?: Record<string, CaseRecord> };
    return { hydrated: true, cases: parsed.cases ?? {} };
  } catch {
    return { hydrated: true, cases: {} };
  }
}

let state: StoreState = typeof window === "undefined" ? SERVER_STATE : load();
const listeners = new Set<() => void>();

function commit(next: StoreState) {
  state = next;
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ cases: next.cases }));
  } catch {
    /* private window or blocked storage: the store still works in memory */
  }
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

const getSnapshot = () => state;
const getServerSnapshot = () => SERVER_STATE;

function update(id: string, change: (record: CaseRecord) => CaseRecord) {
  const base: CaseRecord = state.cases[id] ?? { durations: {}, ui: {} };
  commit({ ...state, cases: { ...state.cases, [id]: change(base) } });
}

export type CaseStoreActions = {
  /** Add the measured time of one agent call to the stage it belongs to. */
  addDuration: (id: string, stage: StageKey, ms: number) => void;
  /** Forget the measured time of stages the backend is about to run again. */
  clearDurations: (id: string, stages: readonly StageKey[]) => void;
  setUi: (id: string, key: string, value: unknown) => void;
  /** Keep only what the backend still agrees with. */
  reconcile: (rows: readonly { obligation_id: string; status: string }[]) => void;
  clearAll: () => void;
};

const actions: CaseStoreActions = {
  addDuration(id, stage, ms) {
    update(id, (record) => ({
      ...record,
      durations: { ...record.durations, [stage]: (record.durations[stage] ?? 0) + ms },
    }));
  },
  clearDurations(id, stages) {
    update(id, (record) => {
      const durations = { ...record.durations };
      for (const stage of stages) delete durations[stage];
      return { ...record, durations };
    });
  },
  setUi(id, key, value) {
    update(id, (record) => ({ ...record, ui: { ...record.ui, [key]: value } }));
  },
  reconcile(rows) {
    const live = new Map(rows.map((row) => [row.obligation_id, row.status]));
    const kept = Object.entries(state.cases).filter(([id]) => {
      const status = live.get(id);
      return status !== undefined && status !== "Pending";
    });
    if (kept.length === Object.keys(state.cases).length) return;
    commit({ ...state, cases: Object.fromEntries(kept) });
  },
  clearAll() {
    commit({ ...state, cases: {} });
  },
};

const StoreContext = createContext<{ state: StoreState; actions: CaseStoreActions } | null>(null);

/** Mounted once at the (app) layout, so it outlives navigation between screens. */
export function CaseStoreProvider({ children }: { children: ReactNode }) {
  const current = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const value = useMemo(() => ({ state: current, actions }), [current]);
  return <StoreContext value={value}>{children}</StoreContext>;
}

function useStore() {
  const store = useContext(StoreContext);
  if (!store) throw new Error("CaseStoreProvider is missing from the layout.");
  return store;
}

export function useCaseStoreActions(): CaseStoreActions {
  return useStore().actions;
}

/** What is remembered about one case, and whether the browser has read it yet. */
export function useCaseRecord(id: string | null) {
  const { state: current, actions: store } = useStore();
  return {
    ready: current.hydrated,
    record: id ? current.cases[id] : undefined,
    store,
  };
}

/**
 * `useState` that survives navigation: the value is kept per case under `key`.
 * Before the browser has read its storage the initial value is used, so the
 * first client render matches the server's.
 */
export function useCaseUi<T>(id: string | null, key: string, initial: T): [T, (next: T) => void] {
  const { ready, record, store } = useCaseRecord(id);
  const stored = ready && record && key in record.ui ? (record.ui[key] as T) : initial;
  const set = useCallback(
    (next: T) => {
      if (id) store.setUi(id, key, next);
    },
    [id, key, store],
  );
  return [stored, set];
}
