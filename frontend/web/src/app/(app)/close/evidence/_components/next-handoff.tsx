"use client";

import Link from "next/link";
import { motion } from "motion/react";

import { PageIcon } from "@/components/ui/icons";
import { cn } from "@/lib/cn";
import { SectionLabel } from "@/components/ui/primitives";
import { easeOutSoft } from "@/lib/motion";
import { routes, withCase } from "@/lib/routes";

import { RAIL } from "../_data";
import { useEvidenceData } from "./data-context";

/**
 * The handoff to the detection agent. The button stays inert until the run
 * finishes; with `autoAdvance` on it also fills as the navigation timer runs.
 */
export function NextHandoff({
  complete,
  autoAdvance,
}: {
  complete: boolean;
  autoAdvance: boolean;
}) {
  const { caseParam } = useEvidenceData();
  const filling = complete && autoAdvance;

  /* Where the handoff goes is the chain's own shape, not this case's data:
     evidence is always followed by detection. The only thing carried across
     is which case is being looked at. */
  const href = withCase(routes.detection, caseParam);

  return (
    <>
      <div className="mt-[30px] h-px bg-sunk" />
      <SectionLabel className="mt-[22px] text-[10.5px] text-faint">
        {RAIL.handoffLabel}
      </SectionLabel>

      <div className="mt-[13px] flex items-center gap-3">
        <PageIcon size={15} className="flex-none text-faint-3" />
        <span className="text-body text-ink">{RAIL.handoffFrom}</span>
        <span className="text-sm text-ghost-2" aria-hidden="true">
          →
        </span>
        <span className="text-body text-ink">{RAIL.handoffTo}</span>
      </div>

      <p className="mt-[9px] pl-[27px] text-meta leading-[1.6] text-pretty text-faint">
        {RAIL.handoffNote}
      </p>

      <motion.div
        initial={false}
        animate={{ opacity: complete ? 1 : 0, y: complete ? 0 : 8 }}
        transition={{ duration: 0.45, ease: easeOutSoft }}
        className="mt-4"
      >
        <Link
          href={href}
          tabIndex={complete ? 0 : -1}
          className={cn(
            "relative block w-full overflow-hidden rounded-xl border border-accent bg-accent px-[14px] py-[11px] text-center text-accent-on transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-accent-deep hover:text-accent-on",
            !complete && "pointer-events-none",
          )}
        >
          <span className="relative z-[2] text-ui font-medium">
            {filling ? RAIL.ctaAuto : RAIL.ctaIdle}
          </span>
          <motion.span
            aria-hidden="true"
            className="absolute top-0 bottom-0 left-0 bg-[rgba(255,255,255,0.22)]"
            initial={false}
            animate={{ width: filling ? "100%" : "0%" }}
            transition={{ duration: 1.2, ease: "linear" }}
          />
        </Link>
      </motion.div>
    </>
  );
}
