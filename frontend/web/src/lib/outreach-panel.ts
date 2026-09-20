"use client";

import { useSyncExternalStore } from "react";

/** Which case's email panel is open, and which of its threads is showing (null = the first). */
type State = { obligationId: string; threadId: string | null } | null;

let state: State = null;
const listeners = new Set<() => void>();

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

/** Lets the ribbon, the run log and the resting messages open the same panel. */
export const outreachPanel = {
  open(obligationId: string, threadId: string | null = null) {
    commit({ obligationId, threadId });
  },
  select(threadId: string) {
    if (state) commit({ ...state, threadId });
  },
  close() {
    commit(null);
  },
};

export function useOutreachPanel(): State {
  return useSyncExternalStore(subscribe, () => state, () => null);
}
