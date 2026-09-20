"use client";

import { useEffect, useState } from "react";
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
  noCases = false,
  periodLabel,
}: {
  rows: CaseRecord[];
  sortKey: SortKey;
  sortDir: SortDir;
  onSort: (key: SortKey) => void;
  onClearFilters: () => void;
  animateRows?: boolean;
  noCases?: boolean;
  periodLabel: string;
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
          key={row.obligationId}
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

      {rows.length === 0 && (
        <CasesEmptyState
          onClear={onClearFilters}
          instant={!!reduceMotion}
          noCases={noCases}
          periodLabel={periodLabel}
        />
      )}
    </div>
  );
}
