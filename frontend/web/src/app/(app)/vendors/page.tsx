"use client";

import { Suspense, useCallback, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

import {
  BackendUnreachable,
  LoadingRows,
  ScreenState,
} from "@/components/ui/screen-state";
import { vendorsPath, withPeriod } from "@/lib/api";
import { ALL_PERIODS, periodLabel } from "@/lib/period";
import { usePeriods } from "@/lib/use-periods";
import { useLiveData } from "@/lib/use-live-data";

import { VendorKpis } from "./_components/vendor-kpis";
import { VendorRail } from "./_components/vendor-rail";
import { VendorTable } from "./_components/vendor-table";
import { VendorsHeader } from "./_components/vendors-header";
import {
  ALL_STATES,
  FILTERS,
  STATE_TONES,
  deriveKpis,
  vendorsIsEmpty,
  type FilterValue,
  type SortDir,
  type SortKey,
  type Vendor,
  type VendorsData,
} from "./_data";

type SortState = { key: SortKey | null; dir: SortDir };

/**
 * `/vendors`, scoped to the month the reader is looking at.
 *
 * `useSearchParams` suspends during the static prerender, so the boundary's
 * fallback renders the same screen with no month chosen; the client fills it
 * in. The screen holds no vendors of its own - they are built from the
 * documents a close reads, so before a month has run there are none.
 */
export default function VendorsPage() {
  return (
    <Suspense fallback={<VendorsScreen period={null} />}>
      <VendorsWithPeriod />
    </Suspense>
  );
}

function VendorsWithPeriod() {
  return <VendorsScreen period={useSearchParams().get("period")} />;
}

function VendorsScreen({ period }: { period: string | null }) {
  const periods = usePeriods();
  /* The URL wins, then whatever month the backend calls current. */
  const selected = period ?? periods.current;
  const scope = selected === ALL_PERIODS ? null : selected;

  const path = useMemo(() => withPeriod(vendorsPath, scope), [scope]);
  const live = useLiveData<VendorsData>(path, { isEmpty: vendorsIsEmpty });
  const vendors = useMemo(() => live.data?.VENDORS ?? [], [live.data]);

  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<FilterValue>(ALL_STATES);
  const [sort, setSort] = useState<SortState>({ key: null, dir: "desc" });
  const [selectedId, setSelectedId] = useState<string | null>(null);

  /** Free-text search spans name, profile, treatment and workflow. */
  const matches = useCallback(
    (vendor: Vendor, ignoreFilter = false) => {
      const q = query.trim().toLowerCase();
      const haystack =
        `${vendor.name} ${vendor.profile} ${vendor.treatment} ${vendor.workflow}`.toLowerCase();
      if (q && !haystack.includes(q)) return false;
      if (!ignoreFilter && filter !== ALL_STATES && vendor.state !== filter) {
        return false;
      }
      return true;
    },
    [query, filter],
  );

  const rows = useMemo(() => {
    const list = vendors.filter((vendor) => matches(vendor));
    if (sort.key === null) return list;
    const key = sort.key;
    const dir = sort.dir === "asc" ? 1 : -1;
    return [...list].sort((a, b) => {
      const x = a[key];
      const y = b[key];
      if (typeof x === "number" && typeof y === "number") return (x - y) * dir;
      return String(x).localeCompare(String(y)) * dir;
    });
  }, [vendors, matches, sort]);

  // Counts ignore the state filter so the menu always shows the full split.
  const filterOptions = useMemo(
    () =>
      FILTERS.map((value) => ({
        value,
        dot: value === ALL_STATES ? "#CFD3CA" : STATE_TONES[value].dot,
        count: vendors.filter(
          (vendor) =>
            matches(vendor, true) &&
            (value === ALL_STATES || vendor.state === value),
        ).length,
      })),
    [vendors, matches],
  );

  /* The reader's pick, if it is still in the list - a month with different
     vendors simply opens on its first. */
  const selectedVendor = useMemo(
    (): Vendor | null =>
      vendors.find((vendor) => vendor.id === selectedId) ?? vendors[0] ?? null,
    [vendors, selectedId],
  );

  /* The headline numerals are counted from the vendors on screen; the
     product holds no figures of its own. */
  const kpis = useMemo(() => deriveKpis(vendors), [vendors]);

  const handleSort = useCallback((key: SortKey) => {
    setSort((prev) => ({
      key,
      dir:
        prev.key === key
          ? prev.dir === "asc"
            ? "desc"
            : "asc"
          : key === "sort"
            ? "desc"
            : "asc",
    }));
  }, []);

  const clearFilters = useCallback(() => {
    setQuery("");
    setFilter(ALL_STATES);
  }, []);

  const month = scope ? periodLabel(scope) : null;
  const subtitle = month
    ? `Vendor context, accounting behavior, and close history across the ${month} close.`
    : "Vendor context, accounting behavior, and close history.";

  return (
    <>
      <main className="flex min-w-[700px] flex-1 flex-col overflow-hidden">
        <div className="flex-none px-[34px] pt-[26px]">
          <VendorsHeader
            query={query}
            onQueryChange={setQuery}
            filter={filter}
            filterOptions={filterOptions}
            onFilterChange={setFilter}
            subtitle={subtitle}
          />
          {live.status === "ready" ? <VendorKpis kpis={kpis} /> : null}
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-[34px] pt-6 pb-[30px]">
          {live.status === "error" ? (
            <BackendUnreachable
              url={live.url}
              error={live.error}
              onRetry={live.retry}
            />
          ) : live.status === "loading" ? (
            <LoadingRows rows={6} />
          ) : live.status === "empty" ? (
            <ScreenState
              title={
                month
                  ? `No close has been run for ${month} yet`
                  : "No close has been run yet"
              }
              body="Vendors are built from the documents a close reads, so this list fills in once the month has run."
              actions={[{ label: "All cases", href: "/cases" }]}
            />
          ) : (
            <VendorTable
              rows={rows}
              selectedId={selectedVendor?.id ?? ""}
              sortKey={sort.key}
              sortDir={sort.dir}
              onSort={handleSort}
              onSelect={setSelectedId}
              onClearFilters={clearFilters}
            />
          )}
        </div>
      </main>

      {live.status === "ready" && selectedVendor ? (
        <VendorRail vendor={selectedVendor} />
      ) : null}
    </>
  );
}
