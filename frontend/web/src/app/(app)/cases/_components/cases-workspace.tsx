"use client";

import { useCallback, useMemo, useState, type ReactNode } from "react";

import type { SortDir } from "@/components/ui/primitives";
import type { PeriodInfo } from "@/lib/period";

import { CasesToolbar } from "./cases-toolbar";
import { CategoryTabs } from "./category-tabs";
import { CaseTable } from "./case-table";
import {
  ALL_STATUSES,
  EMPTY,
  STATUS_OPTIONS,
  countByCategory,
  type CaseRecord,
  type CategoryTab,
  type SortKey,
  type StatusFilter,
} from "../_data";

type Filters = { query: string; tab: CategoryTab; status: StatusFilter };

/** Stable default so the toolbar never rebuilds its menu from a new array. */
const EMPTY_PERIODS: readonly PeriodInfo[] = [];

/** The comp's `matches()`: search text, then category tab, then status. */
function matchesFilters(
  record: CaseRecord,
  { query, tab, status }: Filters,
  ignoreStatus = false,
): boolean {
  const needle = query.trim().toLowerCase();
  if (
    needle &&
    !`${record.vendor} ${record.item} ${record.category} ${record.stage}`
      .toLowerCase()
      .includes(needle)
  ) {
    return false;
  }
  if (tab !== "All" && record.category !== tab) return false;
  if (!ignoreStatus && status !== ALL_STATUSES && record.status !== status) {
    return false;
  }
  return true;
}

/**
 * Everything on this screen that reacts: the filters, the sort, and the rows
 * they produce. The page's title block above is static.
 */
export function CasesWorkspace({
  cases = EMPTY.CASES,
  animateRows = true,
  period = null,
  periods = EMPTY_PERIODS,
  onPeriodChange,
  emptySlot,
}: {
  /** The rows `GET /api/cases` answered with for the selected month. */
  cases?: readonly CaseRecord[];
  animateRows?: boolean;
  /** The selected month, `ALL_PERIODS`, or `null` before one is resolved. */
  period?: string | null;
  periods?: readonly PeriodInfo[];
  onPeriodChange?: (period: string) => void;
  /** Rendered instead of rows when there are none - see `CaseTable`. */
  emptySlot?: ReactNode;
}) {
  const [query, setQuery] = useState("");
  const [tab, setTab] = useState<CategoryTab>("All");
  const [status, setStatus] = useState<StatusFilter>(ALL_STATUSES);
  const [statusMenuOpen, setStatusMenuOpen] = useState(false);
  const [periodMenuOpen, setPeriodMenuOpen] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>("ts");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const filters = useMemo<Filters>(
    () => ({ query, tab, status }),
    [query, tab, status],
  );

  const visible = useMemo(
    () => cases.filter((record) => matchesFilters(record, filters)),
    [cases, filters],
  );

  /* Counts for the tab row come from the rows actually on screen, so a live
     dataset of a different shape never shows the mock's totals. */
  const tabCounts = useMemo(() => countByCategory(cases), [cases]);

  const rows = useMemo(() => {
    const direction = sortDir === "asc" ? 1 : -1;
    return visible.slice().sort((a, b) => {
      const left = a[sortKey];
      const right = b[sortKey];
      if (typeof left === "number" && typeof right === "number") {
        return (left - right) * direction;
      }
      return String(left).localeCompare(String(right)) * direction;
    });
  }, [visible, sortKey, sortDir]);

  const statusCounts = useMemo(() => {
    const pool = cases.filter((record) =>
      matchesFilters(record, filters, true),
    );
    return STATUS_OPTIONS.reduce(
      (counts, option) => {
        counts[option] =
          option === ALL_STATUSES
            ? pool.length
            : pool.filter((record) => record.status === option).length;
        return counts;
      },
      {} as Record<StatusFilter, number>,
    );
  }, [cases, filters]);

  const totals = useMemo(
    () => ({
      total: visible.length,
      active: visible.filter(
        (record) =>
          record.status === "Running" ||
          record.status === "In progress" ||
          record.status === "Queued",
      ).length,
      ready: visible.filter((record) => record.status === "Close-ready").length,
      done: visible.filter((record) => record.status === "Complete").length,
    }),
    [visible],
  );

  /** Same key flips direction; a new key opens on its natural direction. */
  const handleSort = useCallback(
    (key: SortKey) => {
      if (key === sortKey) {
        setSortDir(sortDir === "asc" ? "desc" : "asc");
        return;
      }
      setSortKey(key);
      setSortDir(key === "ts" || key === "amount" ? "desc" : "asc");
    },
    [sortKey, sortDir],
  );

  /* One menu at a time: opening either closes the other, the way a single
     menu bar behaves. */
  const handleStatusMenuOpen = useCallback((open: boolean) => {
    setStatusMenuOpen(open);
    if (open) setPeriodMenuOpen(false);
  }, []);

  const handlePeriodMenuOpen = useCallback((open: boolean) => {
    setPeriodMenuOpen(open);
    if (open) setStatusMenuOpen(false);
  }, []);

  const handlePeriodChange = useCallback(
    (next: string) => onPeriodChange?.(next),
    [onPeriodChange],
  );

  const clearFilters = useCallback(() => {
    setQuery("");
    setTab("All");
    setStatus(ALL_STATUSES);
  }, []);

  return (
    <>
      <div className="flex-none px-[34px]">
        <CasesToolbar
          query={query}
          onQueryChange={setQuery}
          period={period}
          periods={periods}
          periodMenuOpen={periodMenuOpen}
          onPeriodMenuOpenChange={handlePeriodMenuOpen}
          onPeriodChange={handlePeriodChange}
          status={status}
          statusCounts={statusCounts}
          statusMenuOpen={statusMenuOpen}
          onStatusMenuOpenChange={handleStatusMenuOpen}
          onStatusChange={setStatus}
          totals={totals}
        />
        <CategoryTabs value={tab} counts={tabCounts} onChange={setTab} />
      </div>

      <CaseTable
        rows={rows}
        sortKey={sortKey}
        sortDir={sortDir}
        onSort={handleSort}
        onClearFilters={clearFilters}
        animateRows={animateRows}
        emptySlot={cases.length === 0 ? emptySlot : undefined}
      />
    </>
  );
}
