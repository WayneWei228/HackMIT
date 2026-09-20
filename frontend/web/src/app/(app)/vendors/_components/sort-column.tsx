"use client";

import { clsx } from "clsx";

import type { SortDir } from "../_data";

/**
 * A sortable column heading.
 *
 * The shared `ColumnHeader` primitive paints its active caret ink-black; this
 * screen's comp paints it accent green and uses `--color-faint` for the idle
 * label, so the glyph is rebuilt here rather than approximated.
 *
 * `clsx` rather than `cn`: there is nothing to override here, and `cn`'s
 * tailwind-merge is not taught this app's font-size scale, so it reads
 * `text-eyebrow` as a colour and drops it in favour of `text-faint`.
 */
export function SortColumn({
  label,
  active,
  dir,
  onClick,
}: {
  label: string;
  active: boolean;
  dir: SortDir;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        "flex cursor-pointer items-center gap-[7px] text-eyebrow font-medium tracking-[0.12em] select-none transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:text-ink",
        active ? "text-ink" : "text-faint",
      )}
    >
      {label}
      <svg width="10" height="12" viewBox="0 0 10 12" fill="none" className="flex-none">
        <path
          d="M5 1.6L7.4 4.4H2.6z"
          fill={active && dir === "asc" ? "var(--color-accent)" : "var(--color-rule)"}
        />
        <path
          d="M5 10.4L2.6 7.6h4.8z"
          fill={active && dir === "desc" ? "var(--color-accent)" : "var(--color-rule)"}
        />
      </svg>
    </button>
  );
}
