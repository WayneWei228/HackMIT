"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useReducedMotion } from "motion/react";

import { cn } from "@/lib/cn";
import type { SortDir } from "@/components/ui/primitives";

import { CASE_GRID } from "./case-grid";
import { CaseColumnHeader } from "./case-column-header";
import { CaseRow } from "./case-row";
import { CasesEmptyState } from "./cases-empty-state";
import { COLUMNS, type CaseRecord, type SortKey } from "../_data";

/** The comp's first paint: a 450ms rise, rows 45ms apart. */
const ROW_RISE_SECONDS = 0.45;
const ROW_STAGGER_SECONDS = 0.045;

export function CaseTable({
  rows,
  sortKey,
  sortDir,
  onSort,
  onClearFilters,
  animateRows = true,
  emptySlot,
}: {
  rows: CaseRecord[];
  sortKey: SortKey;
  sortDir: SortDir;
  onSort: (key: SortKey) => void;
  onClearFilters: () => void;
  animateRows?: boolean;
  /**
   * What to render instead of rows when there are none. Omitted, the table
   * shows its own "no cases match" state, which is only ever the right answer
   * when the filters are what emptied it. `null` renders nothing at all -
   * what a month still in flight should show.
   */
  emptySlot?: ReactNode;
}) {
  const reduceMotion = useReducedMotion();

  /* The comp's `mounted` latch: the rise plays on the first frame only, so a
     row that arrives later - from a search or a filter - lands immediately.
     `animateRows` is a prop, so this opening value is the same on the server
     and on the client; reduced motion is not, and so only shortens the
     timings below. */
  const [settled, setSettled] = useState(!animateRows);
  useEffect(() => {
    if (settled) return;
    const frame = requestAnimationFrame(() => setSettled(true));
    return () => cancelAnimationFrame(frame);
  }, [settled]);

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-[34px] pt-4 pb-[30px]">
      <div className={cn(CASE_GRID, "border-b border-line px-2.5 pb-[11px]")}>
        {COLUMNS.map((column) => (
          <CaseColumnHeader
            key={column.key}
            label={column.label}
            active={sortKey === column.key}
            dir={sortDir}
            onSort={() => onSort(column.key)}
          />
        ))}
        <div />
      </div>

      {rows.map((row, index) => (
        <CaseRow
          key={`${row.href}-${row.vendor}-${row.item}`}
          row={row}
          entrance={
            settled
              ? null
              : {
                  delay: reduceMotion ? 0 : index * ROW_STAGGER_SECONDS,
                  duration: reduceMotion ? 0 : ROW_RISE_SECONDS,
                }
          }
        />
      ))}

      {rows.length === 0 &&
        (emptySlot === undefined ? (
          <CasesEmptyState onClear={onClearFilters} />
        ) : (
          emptySlot
        ))}
    </div>
  );
}
