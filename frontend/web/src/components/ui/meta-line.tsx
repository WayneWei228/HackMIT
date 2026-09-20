import { Fragment } from "react";

import { cn } from "@/lib/cn";

/**
 * The case's attribute line: treatment, vendor, GL account.
 *
 * One component for all eight close screens, because the alternative was
 * eight copies drifting apart - and they had: two of them set a line-height
 * the others did not, and three nested a second `gap-[15px]` inside the row,
 * so their separators sat 30px from the text instead of 15.
 *
 * The values are real account names and can be long ("GL 1500 · Computer
 * equipment"), so the ROW wraps between items and no item ever breaks inside
 * itself: a phrase split across two lines reads as two attributes. A single
 * item wider than the column is the only case that truncates, and it keeps
 * its full text in a `title`.
 */
export function CaseMetaLine({
  items,
  className,
}: {
  items: readonly string[];
  className?: string;
}) {
  if (items.length === 0) return null;

  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-x-[15px] gap-y-1.5 text-lead leading-[1.35] text-muted-4",
        className,
      )}
    >
      {items.map((item, i) => (
        <Fragment key={`${item}-${i}`}>
          <span className="max-w-full truncate whitespace-nowrap" title={item}>
            {item}
          </span>
          {/* The rule follows its item rather than leading the next one, so a
              wrapped row starts on a word and never on a stray divider. */}
          {i < items.length - 1 ? (
            <span
              aria-hidden="true"
              className="flex-none select-none text-line-dark"
            >
              |
            </span>
          ) : null}
        </Fragment>
      ))}
    </div>
  );
}
