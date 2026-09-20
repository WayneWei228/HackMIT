"use client";

import { useCallback, useEffect, useState } from "react";

import { getJson, healthPath, periodsPath } from "./api";
import { periodLabel, sortPeriods, type PeriodInfo } from "./period";

export type Periods = {
  periods: PeriodInfo[];
  /** The month the backend considers current, if it says. */
  current: string | null;
  /** Whether the backend answered at all. */
  reachable: boolean;
  loading: boolean;
  /** Re-read the list - called after a close, a settlement or a reset. */
  refresh: () => void;
};

type PeriodsPayload = { periods?: unknown; current?: unknown };

function readPeriods(payload: PeriodsPayload | null): PeriodInfo[] {
  if (!payload || !Array.isArray(payload.periods)) return [];
  const out: PeriodInfo[] = [];
  for (const raw of payload.periods) {
    /* `/api/periods` describes a month as an object; `/api/health` only
       lists their names. Both are accepted so the UI works against whichever
       of the two the backend has got to. */
    if (typeof raw === "string") {
      out.push({ period: raw, label: periodLabel(raw) });
      continue;
    }
    if (raw && typeof raw === "object" && "period" in raw) {
      const info = raw as PeriodInfo;
      if (typeof info.period === "string" && info.period) out.push(info);
    }
  }
  return sortPeriods(out);
}

/**
 * Every month the backend knows, and which one it considers current.
 *
 * `GET /api/periods` is the real source. While it is still being built the
 * hook falls back to the month names `/api/health` already carries, so the
 * switcher works against either. With no API at all there are no months to
 * offer, and the screens say so rather than naming one.
 */
export function usePeriods(): Periods {
  const [token, setToken] = useState(0);
  const [state, setState] = useState<{
    periods: PeriodInfo[];
    current: string | null;
    reachable: boolean;
    loading: boolean;
  }>({ periods: [], current: null, reachable: false, loading: true });

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    const settle = (periods: PeriodInfo[], current: string | null) => {
      if (cancelled) return;
      setState({
        periods,
        current: current ?? periods[0]?.period ?? null,
        reachable: true,
        loading: false,
      });
    };

    getJson<PeriodsPayload>(periodsPath, controller.signal)
      .then((payload) => {
        const periods = readPeriods(payload);
        const current =
          typeof payload?.current === "string" ? payload.current : null;
        settle(periods, current);
      })
      .catch(() => {
        /* `/api/periods` is not there yet - fall back to health. */
        if (cancelled) return;
        getJson<PeriodsPayload>(healthPath, controller.signal)
          .then((payload) => settle(readPeriods(payload), null))
          .catch(() => {
            if (cancelled) return;
            /* No backend, so no months. The screens say so rather than
               naming a month the backend never mentioned. */
            setState({
              periods: [],
              current: null,
              reachable: false,
              loading: false,
            });
          });
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [token]);

  const refresh = useCallback(() => setToken((value) => value + 1), []);

  return { ...state, refresh };
}
