"use client";

import {
  PageSubtitle,
  PageTitle,
  SearchField,
} from "@/components/ui/primitives";
import type { FilterValue } from "../_data";
import { FilterMenu, type FilterOption } from "./filter-menu";

/** Page title block plus the search field and agent-state filter. */
export function VendorsHeader({
  query,
  onQueryChange,
  filter,
  filterOptions,
  onFilterChange,
}: {
  query: string;
  onQueryChange: (next: string) => void;
  filter: FilterValue;
  filterOptions: FilterOption[];
  onFilterChange: (next: FilterValue) => void;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-6">
      <div className="min-w-0">
        {/* Not `SectionLabel`: that primitive tracks at 0.13em and its `cn`
            cannot be overridden back to this page eyebrow's 0.15em - see the
            note in sort-column.tsx. A plain class string keeps the tokens. */}
        <div className="text-eyebrow font-medium tracking-caps-xl text-faint-2">
          VENDOR INTELLIGENCE
        </div>
        {/* text-[46px] / leading-[1.05] restore the 46px/1.05 that `cn` strips
            out of `PageTitle`. Same underlying values as text-display. */}
        <PageTitle className="text-[46px] leading-[1.05]">Vendors</PageTitle>
        <PageSubtitle>
          Vendor context, accounting behavior, and close history.
        </PageSubtitle>
      </div>

      <div className="flex flex-none items-center gap-2.5 pb-1">
        <SearchField
          className="w-[212px] max-w-none min-w-0 flex-none"
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder="Search vendors"
          aria-label="Search vendors"
        />
        <FilterMenu
          value={filter}
          options={filterOptions}
          onChange={onFilterChange}
        />
      </div>
    </div>
  );
}
