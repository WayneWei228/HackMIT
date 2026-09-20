"use client";

import { SearchField, StatStrip, Button } from "@/components/ui/primitives";
import { CalendarIcon, ChevronDownIcon } from "@/components/ui/icons";

import { StatusFilterMenu } from "./status-filter-menu";
import type { StatusFilter } from "../_data";

export type CaseTotals = {
  total: number;
  active: number;
  ready: number;
  done: number;
};

/** Search, period, status - and the four serif totals for what survives them. */
export function CasesToolbar({
  query,
  onQueryChange,
  status,
  statusCounts,
  statusMenuOpen,
  onStatusMenuOpenChange,
  onStatusChange,
  totals,
}: {
  query: string;
  onQueryChange: (query: string) => void;
  status: StatusFilter;
  statusCounts: Record<StatusFilter, number>;
  statusMenuOpen: boolean;
  onStatusMenuOpenChange: (open: boolean) => void;
  onStatusChange: (status: StatusFilter) => void;
  totals: CaseTotals;
}) {
  return (
    <div className="mt-[26px] flex flex-wrap items-center justify-between gap-7">
      <div className="flex min-w-[440px] flex-1 items-center gap-2.5">
        <SearchField
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder="Search vendors or close items..."
          aria-label="Search vendors or close items"
        />
        <Button className="text-[13.5px]/[1]">
          <span className="text-muted-3">
            <CalendarIcon />
          </span>
          December 2026
          <span className="flex text-faint-2">
            <ChevronDownIcon size={11} />
          </span>
        </Button>
        <StatusFilterMenu
          value={status}
          counts={statusCounts}
          open={statusMenuOpen}
          onOpenChange={onStatusMenuOpenChange}
          onChange={onStatusChange}
        />
      </div>

      <StatStrip
        size={27}
        stats={[
          { value: totals.total, label: "Total cases" },
          { value: totals.active, label: "Active" },
          { value: totals.ready, label: "Close-ready" },
          { value: totals.done, label: "Complete" },
        ]}
      />
    </div>
  );
}
