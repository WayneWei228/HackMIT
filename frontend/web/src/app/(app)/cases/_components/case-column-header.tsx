"use client";

import type { SortDir } from "@/components/ui/primitives";

/**
 * A sortable column heading.
 *
 * The shared `ColumnHeader` primitive paints the active caret in ink; this
 * screen's comp paints it in TrueUp green and greys the inactive label one
 * step lighter, so the table head is built locally.
 */
export function CaseColumnHeader({
  label,
  active,
  dir,
  onSort,
}: {
  label: string;
  active: boolean;
  dir: SortDir;
  onSort: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSort}
      className={`flex cursor-pointer items-center justify-start gap-[7px] text-eyebrow font-medium tracking-[0.12em] transition-colors duration-[160ms] ease-[var(--ease-out-soft)] select-none hover:text-ink focus-visible:outline-none focus-visible:shadow-[var(--shadow-ring-soft)] ${
        active ? "text-ink" : "text-faint"
      }`}
    >
      {label}
      <svg
        width="10"
        height="12"
        viewBox="0 0 10 12"
        fill="none"
        aria-hidden="true"
        className="flex-none"
      >
        <path
          d="M5 1.6L7.4 4.4H2.6z"
          fill={
            active && dir === "asc"
              ? "var(--color-accent)"
              : "var(--color-rule)"
          }
        />
        <path
          d="M5 10.4L2.6 7.6h4.8z"
          fill={
            active && dir === "desc"
              ? "var(--color-accent)"
              : "var(--color-rule)"
          }
        />
      </svg>
    </button>
  );
}
