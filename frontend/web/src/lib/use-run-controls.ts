"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { getJson, postJson, runStatusPath } from "./api";

/** One line the backend emitted while working. */
export type RunProgress = { at?: string; worker?: string; message?: string };

export type RunStatus = {
  running: boolean;
  action?: string | null;
  period?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  error?: string | null;
  progress?: RunProgress[];
  /** The older shape: one blob of text rather than lines. */
  log_tail?: string | null;
  result?: unknown;
};

export type RunAction =
  /** Close one month. */
  | { kind: "close"; period: string }
  /** Settle one month that has already closed. */
  | { kind: "settle"; period: string }
  /** One month, both phases: the seven agents end to end. */
  | { kind: "run-month"; period: string }
  /** Every month the backend knows about, in order. */
  | { kind: "run-all" }
  | { kind: "reset" };

function actionPath(action: RunAction): string {
  switch (action.kind) {
    case "close":
      return `/api/periods/${encodeURIComponent(action.period)}/close`;
    case "settle":
      return `/api/periods/${encodeURIComponent(action.period)}/settle`;
    case "run-month":
      return `/api/periods/${encodeURIComponent(action.period)}/run`;
    case "run-all":
      return "/api/periods/run-all";
    case "reset":
      return "/api/reset";
  }
}

/** The progress lines, however the backend chose to express them. */
export function progressLines(status: RunStatus | null): string[] {
  if (!status) return [];
  if (Array.isArray(status.progress)) {
    return status.progress
      .map((entry) =>
        [entry.worker, entry.message].filter(Boolean).join(" · "),
      )
      .filter((line) => line.length > 0);
  }
  if (typeof status.log_tail === "string" && status.log_tail.trim()) {
    return status.log_tail.split("\n").filter((line) => line.trim().length > 0);
  }
  return [];
}

const POLL_MS = 1500;

export type RunControls = {
  status: RunStatus | null;
  busy: boolean;
  /** A 400/409 or a network failure, for showing beside the buttons. */
  message: string | null;
  clearMessage: () => void;
  start: (action: RunAction) => void;
};

/**
 * Starting a close, a settlement, a full run or a reset - and watching it.
 *
 * The backend runs one job at a time and answers 409 while one is in flight,
 * so the UI does not queue: it disables the buttons, polls until the job is
 * finished, and then tells the caller to re-read everything it showed. A
 * refusal (400 with a `detail` saying which month must close first) is a
 * message to read, not an error to swallow.
 */
export function useRunControls(onFinished: () => void): RunControls {
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  // Held in a ref so the poll effect does not restart when the caller
  // re-renders with a new callback identity.
  const finishedRef = useRef(onFinished);
  useEffect(() => {
    finishedRef.current = onFinished;
  }, [onFinished]);

  const running = pending || status?.running === true;

  useEffect(() => {
    if (!running) return;
    let cancelled = false;
    const controller = new AbortController();

    const poll = () => {
      getJson<RunStatus>(runStatusPath, controller.signal)
        .then((next) => {
          if (cancelled) return;
          setStatus(next);
          if (next && next.running === false) {
            setPending(false);
            if (next.error) setMessage(String(next.error));
            finishedRef.current();
          }
        })
        .catch(() => {
          /* The API may be restarting; keep polling until it answers. */
        });
    };

    poll();
    const id = setInterval(poll, POLL_MS);
    return () => {
      cancelled = true;
      controller.abort();
      clearInterval(id);
    };
  }, [running]);

  const start = useCallback((action: RunAction) => {
    setMessage(null);
    setPending(true);
    postJson<RunStatus>(actionPath(action)).then((result) => {
      if (result.ok) return;
      /* 409 means a job is already in flight - keep polling rather than
         calling it a failure. Anything else stops here with its reason. */
      if (result.status !== 409) setPending(false);
      setMessage(result.detail);
    });
  }, []);

  const clearMessage = useCallback(() => setMessage(null), []);

  return { status, busy: running, message, clearMessage, start };
}
