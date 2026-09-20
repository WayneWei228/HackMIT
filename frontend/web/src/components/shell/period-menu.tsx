"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";

import { ChevronRightIcon } from "@/components/ui/icons";
import { cn } from "@/lib/cn";
import { popIn, transitions } from "@/lib/motion";
import { ALL_PERIODS, infoLabel, periodLabel, stateLabel } from "@/lib/period";
import { usePeriods } from "@/lib/use-periods";

/** The period a `?case=<period>/<case_key>` value is pinned to. */
function periodOfCase(caseParam: string | null): string | null {
  if (!caseParam) return null;
  const [period] = caseParam.split("/");
  return period || null;
}

/**
 * Which month the reader is looking at, and a way to change it.
 *
 * The month lives in the URL so it survives navigation between the list
 * screens. On a close screen it is not a choice at all - the case belongs to
 * one month - so the chip states the case's period and stops being a menu.
 */
export function PeriodMenu() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const periods = usePeriods();

  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const pinned = periodOfCase(params.get("case"));
  const selected = pinned ?? params.get("period") ?? periods.current;
  const label = selected ? periodLabel(selected) : ALL_PERIODS;

  useEffect(() => {
    if (!open) return;
    const onDocumentClick = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("click", onDocumentClick, true);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("click", onDocumentClick, true);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const choose = (period: string) => {
    const next = new URLSearchParams(params.toString());
    if (period === ALL_PERIODS) next.delete("period");
    else next.set("period", period);
    const query = next.toString();
    router.replace(query ? `${pathname}?${query}` : pathname);
    setOpen(false);
  };

  const body = (
    <>
      <div className="min-w-0 flex-1">
        <div className="truncate text-body text-ink">{label}</div>
        <div className="mt-0.5 text-meta text-faint-2">
          {pinned ? "This case's period" : "Close period"}
        </div>
      </div>
      {pinned ? null : (
        <motion.span
          animate={{ rotate: open ? 90 : 0 }}
          transition={transitions.base}
          className="flex flex-none text-faint-2"
        >
          <ChevronRightIcon />
        </motion.span>
      )}
    </>
  );

  if (pinned) {
    return (
      <div className="flex items-center gap-2.5 rounded-lg px-2.5 py-1.5">
        {body}
      </div>
    );
  }

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={(event) => {
          event.stopPropagation();
          setOpen((value) => !value);
        }}
        className="flex w-full cursor-pointer items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-left transition-colors duration-[160ms] hover:bg-hover"
      >
        {body}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            role="menu"
            variants={popIn}
            initial="hidden"
            animate="visible"
            exit="exit"
            className="absolute bottom-[calc(100%+6px)] left-0 z-20 max-h-[268px] w-[196px] origin-bottom overflow-y-auto rounded-[9px] border border-line bg-panel p-1.5 shadow-[var(--shadow-menu)]"
          >
            {[
              ...periods.periods,
              { period: ALL_PERIODS, label: ALL_PERIODS },
            ].map((info) => {
              const active = (selected ?? ALL_PERIODS) === info.period;
              return (
                <button
                  key={info.period}
                  type="button"
                  role="menuitemradio"
                  aria-checked={active}
                  onClick={() => choose(info.period)}
                  className={cn(
                    "flex w-full cursor-pointer items-center gap-2.5 rounded-md px-2.5 py-2 text-ui transition-colors duration-[140ms] ease-[var(--ease-out-soft)] hover:bg-[#F3F3EE] focus-visible:bg-[#F3F3EE] focus-visible:outline-none",
                    active ? "bg-accent-tint text-ink" : "text-ink-2",
                  )}
                >
                  <span className="flex-1 truncate text-left">
                    {infoLabel(info)}
                  </span>
                  {info.state ? (
                    <span className="flex-none text-meta text-ghost">
                      {stateLabel(info.state)}
                    </span>
                  ) : null}
                </button>
              );
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
