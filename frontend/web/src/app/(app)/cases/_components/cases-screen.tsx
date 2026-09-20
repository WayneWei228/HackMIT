"use client";

import { useCallback, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { BackendUnreachable, LoadingRows } from "@/components/ui/screen-state";
import { casesPath, withPeriod } from "@/lib/api";
import { ALL_PERIODS, infoLabel, type PeriodInfo } from "@/lib/period";
import { routes, withPeriodParam } from "@/lib/routes";
import { useLiveData } from "@/lib/use-live-data";
import { usePeriods } from "@/lib/use-periods";
import { useRunControls } from "@/lib/use-run-controls";

import { CasesHeader } from "./cases-header";
import { CasesWorkspace } from "./cases-workspace";
import { PeriodEmptyState } from "./cases-empty-state";
import { periodActions } from "./period-actions";
import { EMPTY, type CasesData } from "../_data";

/** A month the backend answered for but has not run is "nothing to show". */
const isEmpty = (data: CasesData) => data.CASES.length === 0;

/**
 * The case list.
 *
 * Everything here comes from `GET /api/cases`, scoped to the month in
 * `?period=`. Nothing is pre-loaded and no month is assumed to exist: the
 * backend starts empty, the switcher lists whatever months it knows, and an
 * unrun month is an empty state with the run that would fill it - not a
 * demo dataset standing in for one.
 */
export function CasesScreen({ periodParam }: { periodParam: string | null }) {
  const router = useRouter();
  const periods = usePeriods();
  const refreshPeriods = periods.refresh;

  /* Bumped when a run finishes: the fetch is keyed on the path, so a changed
     path is the only way to ask for the month again. */
  const [runToken, setRunToken] = useState(0);

  /* The URL wins; otherwise the month the backend calls current, otherwise
     the newest it knows. `null` only while nothing is known yet. */
  const period =
    periodParam ?? periods.current ?? periods.periods[0]?.period ?? null;
  const resolving = periodParam === null && periods.loading;

  const path = useMemo(() => {
    if (resolving) return null;
    const base =
      period !== null && period !== ALL_PERIODS
        ? withPeriod(casesPath, period)
        : casesPath;
    if (runToken === 0) return base;
    return `${base}${base.includes("?") ? "&" : "?"}run=${runToken}`;
  }, [resolving, period, runToken]);

  const live = useLiveData<CasesData>(path, { isEmpty });

  const onFinished = useCallback(() => {
    refreshPeriods();
    setRunToken((token) => token + 1);
  }, [refreshPeriods]);

  const controls = useRunControls(onFinished);

  const info = useMemo(
    (): PeriodInfo | null =>
      period === null || period === ALL_PERIODS
        ? null
        : (periods.periods.find((entry) => entry.period === period) ?? null),
    [periods.periods, period],
  );

  const scoped = period !== null && period !== ALL_PERIODS;
  const actions = periodActions(info);
  const canClose = scoped && actions.canClose;
  const canSettle = scoped && actions.canSettle;

  const handlePeriodChange = useCallback(
    (next: string) => {
      controls.clearMessage();
      router.replace(withPeriodParam(routes.cases, next), { scroll: false });
    },
    [controls, router],
  );

  /**
   * The month standing in the way of this one.
   *
   * Months close in order, so a month that offers no run is waiting on an
   * earlier one - the same rule the API states when it refuses ("months
   * close in order"). The screen already holds the whole month list, so it
   * can name the blocker without a round-trip. A settled month is finished
   * rather than blocked, and keeps its own wording.
   */
  const blockedBy = useMemo(() => {
    if (!scoped || !actions.known) return null;
    if (canClose || canSettle) return null;
    if (info?.state !== "NOT_RUN") return null;
    /* `periods.periods` is newest-first, and only a month *earlier* than
       this one can be holding it up - the blocker is the earliest month
       that has not run. */
    const blocker = periods.periods
      .filter((entry) => entry.state === "NOT_RUN" && entry.period < period)
      .at(-1);
    if (!blocker) return null;
    return {
      label: infoLabel(blocker),
      href: withPeriodParam(routes.cases, blocker.period),
    };
  }, [scoped, actions.known, canClose, canSettle, info, periods.periods, period]);

  /** The run the empty state offers, and the one its button starts. */
  const runLabel = !scoped
    ? "Run all months"
    : canClose
      ? "Run close"
      : canSettle
        ? "Run settlement"
        : null;

  const runSelected = useCallback(() => {
    if (period === null || period === ALL_PERIODS) {
      controls.start({ kind: "run-all" });
      return;
    }
    if (canClose) controls.start({ kind: "close", period });
    else if (canSettle) controls.start({ kind: "settle", period });
  }, [period, canClose, canSettle, controls]);

  if (live.status === "error") {
    return (
      <>
        {/* With the backend down, the only month we can honestly name is the
            one in the URL - `usePeriods` is guessing at this point. */}
        <CasesHeader
          period={periodParam}
          info={null}
          canClose={false}
          canSettle={false}
          controls={controls}
          showRunStrip={false}
        />
        <div className="min-h-0 flex-1 overflow-y-auto px-[34px] pt-6 pb-[30px]">
          <BackendUnreachable
            url={live.url}
            error={live.error}
            onRetry={live.retry}
          />
        </div>
      </>
    );
  }

  /* Waiting for the month list is still waiting - not an empty month. */
  const emptySlot =
    resolving || live.status === "loading" ? (
      <LoadingRows rows={6} className="pt-4" />
    ) : (
      <PeriodEmptyState
        period={period}
        actionLabel={runLabel}
        reason={controls.message}
        blockedBy={blockedBy}
        busy={controls.busy}
        onRun={runSelected}
      />
    );

  return (
    <>
      <CasesHeader
        period={period}
        info={info}
        canClose={canClose}
        canSettle={canSettle}
        controls={controls}
        /* Held back until there is a month to run, so the strip does not
           reshuffle its buttons the moment the month list lands. */
        showRunStrip={!resolving}
      />
      <CasesWorkspace
        cases={live.data?.CASES ?? EMPTY.CASES}
        period={period}
        periods={periods.periods}
        onPeriodChange={handlePeriodChange}
        emptySlot={emptySlot}
      />
    </>
  );
}
