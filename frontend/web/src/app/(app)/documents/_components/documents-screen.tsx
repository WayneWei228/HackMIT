"use client";

import { useMemo } from "react";

import {
  BackendUnreachable,
  LoadingRows,
  ScreenState,
} from "@/components/ui/screen-state";
import { withPeriod } from "@/lib/api";
import { ALL_PERIODS, periodLabel, type PeriodInfo } from "@/lib/period";
import { routes, withPeriodParam } from "@/lib/routes";
import { useLiveData } from "@/lib/use-live-data";
import { usePeriods } from "@/lib/use-periods";

import { DocumentsHeader } from "./documents-header";
import { DocumentTable } from "./document-table";
import { documentsIsEmpty, type DocumentsData } from "../_data";

/** `GET /api/documents` - the files a close read. */
const documentsPath = "/api/documents";

/**
 * The document list.
 *
 * Everything here comes from `GET /api/documents`, scoped to the month in
 * `?period=`. A month with no documents is a month whose files have not
 * landed yet, and says so rather than showing somebody else's paperwork.
 */
export function DocumentsScreen({
  periodParam,
}: {
  periodParam: string | null;
}) {
  const periods = usePeriods();

  /* The URL wins; otherwise the month the backend calls current, otherwise
     the newest it knows. `null` only while nothing is known yet. */
  const period =
    periodParam ?? periods.current ?? periods.periods[0]?.period ?? null;
  const resolving = periodParam === null && periods.loading;
  const scope = period === ALL_PERIODS ? null : period;

  const path = useMemo(
    () => (resolving ? null : withPeriod(documentsPath, scope)),
    [resolving, scope],
  );

  const live = useLiveData<DocumentsData>(path, { isEmpty: documentsIsEmpty });

  const info = useMemo(
    (): PeriodInfo | null =>
      period === null || period === ALL_PERIODS
        ? null
        : (periods.periods.find((entry) => entry.period === period) ?? null),
    [periods.periods, period],
  );

  return (
    <>
      <DocumentsHeader period={resolving ? periodParam : period} info={info} />

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
          <EmptyMonth period={period} />
        ) : (
          <DocumentTable docs={live.data?.documents ?? []} />
        )}
      </div>
    </>
  );
}

/** The month answered, and had no documents in it. */
function EmptyMonth({ period }: { period: string | null }) {
  const scoped = period !== null && period !== ALL_PERIODS;
  const label = scoped ? periodLabel(period) : null;

  return (
    <ScreenState
      title={
        label ? `No documents for ${label} yet` : "No documents have arrived yet"
      }
      body="A month's documents are the files the close reads for it, so this list fills in as they land."
      actions={[
        {
          label: "All cases",
          href: withPeriodParam(routes.cases, scoped ? period : null),
        },
      ]}
    />
  );
}
