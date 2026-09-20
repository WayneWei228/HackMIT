"use client";

import { motion, useReducedMotion } from "motion/react";

import { Button } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import { staggerParent } from "@/lib/motion";
import { COLUMNS, type SortDir, type SortKey, type Vendor } from "../_data";
import { VENDOR_GRID } from "./grid";
import { SortColumn } from "./sort-column";
import { VendorRow } from "./vendor-row";

export function VendorTable({
  rows,
  selectedId,
  sortKey,
  sortDir,
  onSort,
  onSelect,
  onClearFilters,
}: {
  rows: Vendor[];
  selectedId: string;
  sortKey: SortKey | null;
  sortDir: SortDir;
  onSort: (key: SortKey) => void;
  onSelect: (id: string) => void;
  onClearFilters: () => void;
}) {
  const reduced = useReducedMotion();

  return (
    <>
      <div className={cn(VENDOR_GRID, "border-b border-line px-3 pb-[11px]")}>
        {COLUMNS.map((column) => (
          <SortColumn
            key={column.key}
            label={column.label}
            active={sortKey === column.key}
            dir={sortDir}
            onClick={() => onSort(column.key)}
          />
        ))}
        <div />
      </div>

      <motion.div
        variants={staggerParent(0.05)}
        initial={reduced ? false : "hidden"}
        animate="visible"
      >
        {rows.map((vendor) => (
          <VendorRow
            key={vendor.id}
            vendor={vendor}
            selected={vendor.id === selectedId}
            animateLayout={!reduced}
            onSelect={() => onSelect(vendor.id)}
          />
        ))}
      </motion.div>

      {rows.length === 0 && (
        <div className="flex flex-col items-center justify-center gap-2.5 px-5 py-16">
          <div className="font-display text-[22px] text-ink-deep">
            No vendors match
          </div>
          <div className="text-ui text-faint">
            Try a different search term or clear the filter.
          </div>
          <Button
            className="mt-1.5 py-[9px] text-[13.5px] leading-none"
            onClick={onClearFilters}
          >
            Clear filters
          </Button>
        </div>
      )}
    </>
  );
}
