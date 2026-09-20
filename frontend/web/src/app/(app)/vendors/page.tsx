"use client";

import { useCallback, useMemo, useState } from "react";

import { VendorKpis } from "./_components/vendor-kpis";
import { VendorRail } from "./_components/vendor-rail";
import { VendorTable } from "./_components/vendor-table";
import { VendorsHeader } from "./_components/vendors-header";
import {
  ALL_STATES,
  DEFAULT_VENDOR_ID,
  FILTERS,
  STATE_TONES,
  VENDORS,
  type FilterValue,
  type SortDir,
  type SortKey,
  type Vendor,
} from "./_data";

type SortState = { key: SortKey | null; dir: SortDir };

export default function VendorsPage() {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<FilterValue>(ALL_STATES);
  const [sort, setSort] = useState<SortState>({ key: null, dir: "desc" });
  const [selectedId, setSelectedId] = useState(DEFAULT_VENDOR_ID);

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
    const list = VENDORS.filter((vendor) => matches(vendor));
    if (sort.key === null) return list;
    const key = sort.key;
    const dir = sort.dir === "asc" ? 1 : -1;
    return [...list].sort((a, b) => {
      const x = a[key];
      const y = b[key];
      if (typeof x === "number" && typeof y === "number") return (x - y) * dir;
      return String(x).localeCompare(String(y)) * dir;
    });
  }, [matches, sort]);

  // Counts ignore the state filter so the menu always shows the full split.
  const filterOptions = useMemo(
    () =>
      FILTERS.map((value) => ({
        value,
        dot: value === ALL_STATES ? "#CFD3CA" : STATE_TONES[value].dot,
        count: VENDORS.filter(
          (vendor) =>
            matches(vendor, true) &&
            (value === ALL_STATES || vendor.state === value),
        ).length,
      })),
    [matches],
  );

  const selected = useMemo(
    () => VENDORS.find((vendor) => vendor.id === selectedId) ?? VENDORS[0],
    [selectedId],
  );

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
          />
          <VendorKpis />
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-[34px] pb-[30px]">
          <VendorTable
            rows={rows}
            selectedId={selected.id}
            sortKey={sort.key}
            sortDir={sort.dir}
            onSort={handleSort}
            onSelect={setSelectedId}
            onClearFilters={clearFilters}
          />
        </div>
      </main>

      <VendorRail vendor={selected} />
    </>
  );
}
