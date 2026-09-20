"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";

import { cn } from "@/lib/cn";
import { MoreIcon } from "@/components/ui/icons";
import { easeOutSoft, popIn } from "@/lib/motion";
import { setAutoRun } from "@/lib/use-auto-run";

import { CASE_GRID } from "./case-grid";
import { CaseStatusDot } from "./case-status-dot";
import {
  CATEGORY_STYLES,
  MARKS,
  formatAmount,
  type CaseRecord,
} from "../_data";

const MotionLink = motion.create(Link);

/**
 * The comp's entrance: a 7px rise over 450ms, rows 45ms apart. It runs once,
 * when the table first paints. A row that arrives later - because the search
 * or a filter changed - appears immediately, exactly as the comp does.
 *
 * `null` means the table has already settled. Reduced motion zeroes the
 * numbers rather than dropping the object, so the markup React renders on the
 * server and the markup it hydrates are identical either way.
 */
export type CaseRowEntrance = { delay: number; duration: number } | null;

/** One case: vendor, close item, amount, where the agent chain has got to. */
export function CaseRow({
  row,
  entrance,
}: {
  row: CaseRecord;
  entrance: CaseRowEntrance;
}) {
  const router = useRouter();

  /* A live row may carry a mark index past the end of the palette, or a
     category the palette has no swatch for; neither is worth a blank screen. */
  const mark = MARKS[row.mark] ?? MARKS[0];
  const category = CATEGORY_STYLES[row.category] ?? {
    bg: "var(--color-wash-cool)",
    fg: "var(--color-ink-2)",
  };

  /* Frozen at mount so a later re-render cannot restart or cut short a rise
     that is already playing. */
  const [entranceOnMount] = useState(entrance);

  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  /* Same dismissal as the toolbar's menus: anywhere else, or Escape. */
  useEffect(() => {
    if (!menuOpen) return;
    const onDocumentClick = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setMenuOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenuOpen(false);
    };
    document.addEventListener("click", onDocumentClick, true);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("click", onDocumentClick, true);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [menuOpen]);

  /**
   * Open this case with the chain playing itself.
   *
   * The row's own href is the destination either way - the only difference is
   * the auto-run flag, which lives outside React precisely so it survives the
   * navigation it causes.
   */
  const runAgents = () => {
    setMenuOpen(false);
    setAutoRun(true);
    router.push(row.href);
  };

  return (
    <MotionLink
      href={row.href}
      initial={entranceOnMount ? { opacity: 0, y: 7 } : false}
      animate={{ opacity: 1, y: 0 }}
      transition={
        entranceOnMount
          ? {
              duration: entranceOnMount.duration,
              ease: easeOutSoft,
              delay: entranceOnMount.delay,
            }
          : { duration: 0 }
      }
      className={cn(
        CASE_GRID,
        "rounded-xl border-b border-wash-cool px-2.5 py-[15px] text-ink transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-[#F7F7F2]",
        /* While the menu is open this row has to paint above the rows below
           it, which come later in the document. */
        menuOpen && "relative z-20",
      )}
    >
      <div className="flex min-w-0 items-center gap-[14px]">
        <span
          className="flex h-8 w-8 flex-none items-center justify-center rounded-xl text-meta font-semibold tracking-[0.02em]"
          style={{ background: mark.bg, color: mark.fg }}
        >
          {row.initials}
        </span>
        <span className="truncate text-nav text-ink">{row.vendor}</span>
      </div>

      <div className="truncate text-body text-ink-2">{row.item}</div>

      {/* "Accounts Payable" is a phrase, not two words that may fall apart:
          the pill holds one line and clips, with the full value on hover. */}
      <div className="min-w-0">
        <span
          title={row.category}
          className="inline-block max-w-full truncate rounded-md px-2.5 py-[5px] align-middle text-meta whitespace-nowrap"
          style={{ background: category.bg, color: category.fg }}
        >
          {row.category}
        </span>
      </div>

      <div className="text-body text-ink tabular-nums">
        {formatAmount(row.amount)}
      </div>

      <div className="truncate text-body whitespace-nowrap text-ink-2" title={row.stage}>
        {row.stage}
      </div>

      <div className="flex min-w-0 items-center gap-2.5">
        <CaseStatusDot status={row.status} />
        <span
          title={row.status}
          className="truncate text-body whitespace-nowrap text-ink-2"
        >
          {row.status}
        </span>
      </div>

      <div className="text-sm leading-[1.45] text-faint">
        <div>{row.date}</div>
        <div>{row.time}</div>
      </div>

      <div ref={menuRef} className="relative flex justify-end">
        <button
          type="button"
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          aria-label={`Actions for ${row.vendor}`}
          onClick={(event) => {
            /* The row is a link: without both of these, opening the menu
               would navigate to the case instead. */
            event.preventDefault();
            event.stopPropagation();
            setMenuOpen((open) => !open);
          }}
          className="-mr-1 flex h-7 w-7 cursor-pointer items-center justify-center rounded-md border border-transparent text-ghost-2 transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-wash-cool hover:text-muted-3 focus-visible:bg-wash-cool focus-visible:text-muted-3 focus-visible:outline-none"
        >
          <MoreIcon className="text-[15px]" />
        </button>

        <AnimatePresence>
          {menuOpen && (
            <motion.div
              role="menu"
              variants={popIn}
              initial="hidden"
              animate="visible"
              exit="exit"
              className="origin-top-right absolute top-[calc(100%+6px)] right-0 z-30 min-w-[164px] rounded-[9px] border border-line bg-panel p-1.5 shadow-[var(--shadow-menu)]"
            >
              <button
                type="button"
                role="menuitem"
                onClick={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  runAgents();
                }}
                className="flex w-full cursor-pointer items-center rounded-md px-2.5 py-2 text-ui whitespace-nowrap text-ink-2 transition-colors duration-[140ms] ease-[var(--ease-out-soft)] hover:bg-[#F3F3EE] focus-visible:bg-[#F3F3EE] focus-visible:outline-none"
              >
                Run agents
              </button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </MotionLink>
  );
}
