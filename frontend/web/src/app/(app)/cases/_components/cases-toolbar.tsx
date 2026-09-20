"use client";

import { SearchField, StatStrip } from "@/components/ui/primitives";
import { CalendarIcon } from "@/components/ui/icons";

import { StatusFilterMenu } from "./status-filter-menu";
import type { StatusFilter } from "../_data";

export type CaseTotals = {
  total: number;
  pending: number;
  active: number;
  ready: number;
  done: number;
};

/** Search, period, status - and the serif totals for what survives them. */
export function CasesToolbar({
  query,
  onQueryChange,
  periodLabel,
  status,
  statusCounts,
  statusMenuOpen,
  onStatusMenuOpenChange,
  onStatusChange,
  totals,
}: {
  query: string;
  onQueryChange: (query: string) => void;
  periodLabel: string;
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
        {/* Not a button: the comp's month picker opened a period switcher
            with no backend behind it, so this only displays the close's
            actual period from the API instead of offering a control. */}
        {periodLabel && (
          <div className="flex items-center gap-2.5 rounded-xl whitespace-nowrap border border-line-soft bg-panel px-3.5 py-[11px] text-[13.5px]/[1] text-ink-2">
            <span className="text-muted-3">
              <CalendarIcon />
            </span>
            {periodLabel}
          </div>
        )}
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
          { value: totals.pending, label: "Pending" },
          { value: totals.active, label: "Active" },
          { value: totals.ready, label: "Close-ready" },
          { value: totals.done, label: "Complete" },
        ]}
      />
    </div>
  );
}
