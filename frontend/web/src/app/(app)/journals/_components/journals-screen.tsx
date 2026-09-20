"use client";

import { useMemo } from "react";

import {
  BackendUnreachable,
  LoadingRows,
  ScreenState,
} from "@/components/ui/screen-state";
import { journalsPath, withPeriod } from "@/lib/api";
import { ALL_PERIODS, periodLabel, type PeriodInfo } from "@/lib/period";
import { routes, withPeriodParam } from "@/lib/routes";
import { useLiveData } from "@/lib/use-live-data";
import { usePeriods } from "@/lib/use-periods";

import { JournalsHeader } from "./journals-header";
import { JournalTable } from "./journal-table";
import { journalsIsEmpty, type JournalsData } from "../_data";

/** `GET /api/journals` - the entries a close posted. */

/**
 * The journal list.
 *
 * Everything here comes from `GET /api/journals`, scoped to the month in
 * `?period=`. Nothing is pre-loaded: a month holds no entries until its close
 * has been run, and an unrun month is an empty state rather than a stand-in
 * dataset.
 */
export function JournalsScreen({ periodParam }: { periodParam: string | null }) {
  const periods = usePeriods();

  /* The URL wins; otherwise the month the backend calls current, otherwise
     the newest it knows. `null` only while nothing is known yet. */
  const period =
    periodParam ?? periods.current ?? periods.periods[0]?.period ?? null;
  const resolving = periodParam === null && periods.loading;
  const scope = period === ALL_PERIODS ? null : period;

  const path = useMemo(
    () => (resolving ? null : withPeriod(journalsPath, scope)),
    [resolving, scope],
  );

  const live = useLiveData<JournalsData>(path, { isEmpty: journalsIsEmpty });

  const info = useMemo(
    (): PeriodInfo | null =>
      period === null || period === ALL_PERIODS
        ? null
        : (periods.periods.find((entry) => entry.period === period) ?? null),
    [periods.periods, period],
  );

  return (
    <>
      <JournalsHeader period={resolving ? periodParam : period} info={info} />

      <div className="min-h-0 flex-1 overflow-y-auto px-[34px] pt-6 pb-[30px]">
        {live.status === "error" ? (
          <BackendUnreachable
            url={live.url}
            error={live.error}
            onRetry={live.retry}
          />
        ) : resolving || live.status === "loading" ? (
          <LoadingRows rows={6} />
        ) : live.status === "empty" ? (
          <EmptyMonth period={period} info={info} />
        ) : (
          <JournalTable
            entries={live.data?.journals ?? []}
            note={live.data?.note}
          />
        )}
      </div>
    </>
  );
}

/**
 * The month answered, and had no entries in it.
 *
 * Which is two different facts. A month that has not been run holds nothing
 * at all, and the thing to say is how it gets filled. A month that *has* run
 * and still posted no entries is a finished month with an empty ledger, and
 * saying "no close has been run" about it would be false.
 */
function EmptyMonth({
  period,
  info,
}: {
  period: string | null;
  info: PeriodInfo | null;
}) {
  const scoped = period !== null && period !== ALL_PERIODS;
  const label = scoped ? periodLabel(period) : null;
  const notRun = info?.state === "NOT_RUN" || info?.state === undefined;

  const title = notRun
    ? label
      ? `No close has been run for ${label} yet`
      : "No close has been run yet"
    : `No journal entries for ${label}`;

  return (
    <ScreenState
      title={title}
      body={
        notRun
          ? "Every entry on this screen is posted by the close when it runs over that month's documents."
          : "This month's close posted no entries - nothing it found had to be booked."
      }
      actions={[
        {
          label: "All cases",
          href: withPeriodParam(routes.cases, scoped ? period : null),
        },
      ]}
    />
  );
}
