"use client";

import { useCallback, useMemo, useState } from "react";

import type { SortDir } from "@/components/ui/primitives";

import { CasesToolbar } from "./cases-toolbar";
import { CategoryTabs } from "./category-tabs";
import { CaseTable } from "./case-table";
import { compareMoney } from "@/lib/money";

import {
  ALL_STATUSES,
  CATEGORY_ORDER,
  STATUS_OPTIONS,
  type CaseRecord,
  type CategoryTab,
  type SortKey,
  type StatusFilter,
} from "../_data";

type Filters = { query: string; tab: CategoryTab; status: StatusFilter };

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
  cases,
  animateRows = true,
}: {
  cases: readonly CaseRecord[];
  animateRows?: boolean;
}) {
  const [query, setQuery] = useState("");
  const [tab, setTab] = useState<CategoryTab>("All");
  const [status, setStatus] = useState<StatusFilter>(ALL_STATUSES);
  const [statusMenuOpen, setStatusMenuOpen] = useState(false);
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

  const tabs = useMemo<CategoryTab[]>(
    () => [
      "All",
      ...CATEGORY_ORDER.filter((category) =>
        cases.some((record) => record.category === category),
      ),
    ],
    [cases],
  );

  const tabCounts = useMemo(
    () =>
      Object.fromEntries(
        tabs.map((tab) => [
          tab,
          tab === "All"
            ? cases.length
            : cases.filter((record) => record.category === tab).length,
        ]),
      ) as Record<CategoryTab, number>,
    [cases, tabs],
  );

  const rows = useMemo(() => {
    const direction = sortDir === "asc" ? 1 : -1;
    return visible.slice().sort((a, b) => {
      if (sortKey === "amount") {
        return compareMoney(a.amount, b.amount) * direction;
      }
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
      pending: visible.filter((record) => record.status === "Pending").length,
      active: visible.filter(
        (record) =>
          record.status === "Running" ||
          record.status === "In progress" ||
          record.status === "Waiting" ||
          record.status === "Needs review",
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
          status={status}
          statusCounts={statusCounts}
          statusMenuOpen={statusMenuOpen}
          onStatusMenuOpenChange={setStatusMenuOpen}
          onStatusChange={setStatus}
          totals={totals}
        />
        <CategoryTabs
          tabs={tabs}
          counts={tabCounts}
          value={tab}
          onChange={setTab}
        />
      </div>

      <CaseTable
        rows={rows}
        sortKey={sortKey}
        sortDir={sortDir}
        onSort={handleSort}
        onClearFilters={clearFilters}
        animateRows={animateRows}
        noCases={cases.length === 0}
      />
    </>
  );
}
