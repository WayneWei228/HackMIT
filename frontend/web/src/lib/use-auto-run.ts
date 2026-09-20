"use client";

import { useCallback, useEffect, useSyncExternalStore } from "react";

/**
 * "Auto-run agents": play the whole chain without clicking.
 *
 * The setting has to survive the navigation it causes - each hand-off is a
 * real page load of the next agent's screen - so it lives outside React. It
 * is kept in `localStorage` rather than threaded through every link, because
 * a URL flag would mean touching all twenty-odd hrefs in the chain and any
 * one of them forgetting it would silently stop the run. `?auto=1` is still
 * honoured on arrival, so a link from the case list can switch it on.
 */
const KEY = "trueup.auto-run";

const listeners = new Set<() => void>();

function read(): boolean {
  try {
    return window.localStorage.getItem(KEY) === "1";
  } catch {
    /* Private windows and blocked storage: the run simply does not persist. */
    return false;
  }
}

function write(value: boolean) {
  try {
    if (value) window.localStorage.setItem(KEY, "1");
    else window.localStorage.removeItem(KEY);
  } catch {
    /* Ignored - the toggle still works for this page. */
  }
  for (const listener of listeners) listener();
}

/** Turn the chain on before navigating to it, from outside React. */
export function setAutoRun(value: boolean) {
  if (typeof window === "undefined") return;
  write(value);
}

function subscribe(onChange: () => void) {
  listeners.add(onChange);
  window.addEventListener("storage", onChange);
  return () => {
    listeners.delete(onChange);
    window.removeEventListener("storage", onChange);
  };
}

export type AutoRun = {
  /** Whether the chain should advance on its own. */
  auto: boolean;
  setAuto: (value: boolean) => void;
  toggle: () => void;
};

export function useAutoRun(): AutoRun {
  const auto = useSyncExternalStore(
    subscribe,
    read,
    () => false, // the server cannot know; the chain never starts there
  );

  /* A link may ask for the chain: `?auto=1` switches it on, `?auto=0` off. */
  useEffect(() => {
    const value = new URLSearchParams(window.location.search).get("auto");
    if (value === "1") write(true);
    else if (value === "0") write(false);
  }, []);

  const setAuto = useCallback((value: boolean) => write(value), []);
  const toggle = useCallback(() => write(!read()), []);

  return { auto, setAuto, toggle };
}
