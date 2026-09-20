"use client";

import Link from "next/link";
import { AnimatePresence, motion } from "motion/react";

import { riseIn, transitions } from "@/lib/motion";
import { routes } from "@/lib/routes";

import {
  CTA_ADVANCING_LABEL,
  CTA_IDLE_LABEL,
  HANDOFF_BLURB,
  HANDOFF_FROM,
  HANDOFF_TO,
  type SourceId,
} from "../_data";
import { SourcePageIcon } from "./close-icons";
import { RailLabel } from "./rail-label";

/**
 * What ingestion is about to hand over: the files it picked, and the link that
 * starts the evidence agent.
 *
 * The comp navigates on its own once the run lands. Here that is opt-in, so
 * the button below is the thing that moves the close forward.
 */
export function RailHandoff({
  files,
  complete,
  autoAdvance,
}: {
  files: { id: SourceId; name: string }[];
  complete: boolean;
  autoAdvance: boolean;
}) {
  const advancing = complete && autoAdvance;

  return (
    <>
      <div className="mt-8 h-px bg-sunk" />
      <div className="mt-[22px]">
        <RailLabel>SELECTED FILES ({files.length})</RailLabel>
      </div>
      <div className="mt-3 flex flex-col">
        <AnimatePresence initial={false}>
          {files.map((file) => (
            <motion.button
              key={file.id}
              type="button"
              layout
              variants={riseIn}
              initial="hidden"
              animate="visible"
              exit="hidden"
              transition={transitions.base}
              className="-mx-2 flex cursor-pointer items-center gap-3 rounded-md px-2 py-[7px] text-left transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-[#F1F1EB]"
            >
              <SourcePageIcon
                width={15}
                height={17}
                className="flex-none text-faint-3"
              />
              <span className="text-ui text-ink">{file.name}</span>
            </motion.button>
          ))}
        </AnimatePresence>
      </div>

      <div className="mt-[30px] h-px bg-sunk" />
      <div className="mt-[22px]">
        <RailLabel>NEXT HANDOFF</RailLabel>
      </div>
      <Link
        href={routes.evidence}
        className="-mx-2 mt-[13px] flex items-center gap-3 rounded-lg px-2 py-1.5 text-ink transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-[#F1F1EB] hover:text-ink"
      >
        <SourcePageIcon width={15} height={17} className="flex-none text-faint-3" />
        <span className="text-body text-ink">{HANDOFF_FROM}</span>
        <span aria-hidden="true" className="text-sm text-ghost-2">
          →
        </span>
        <span className="text-body text-ink">{HANDOFF_TO}</span>
      </Link>
      <div className="mt-[9px] pl-[27px] text-meta leading-[1.6] text-pretty text-faint">
        {HANDOFF_BLURB}
      </div>

      <motion.div
        animate={{ opacity: complete ? 1 : 0.55 }}
        transition={transitions.slow}
        className="mt-4"
      >
        <Link
          href={routes.evidence}
          className="relative block w-full overflow-hidden rounded-xl border border-accent bg-accent px-3.5 py-[11px] text-center text-ui font-medium text-accent-on transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-accent-deep hover:text-accent-on"
        >
          <span className="relative z-[2]">
            {advancing ? CTA_ADVANCING_LABEL : CTA_IDLE_LABEL}
          </span>
          <motion.span
            aria-hidden="true"
            initial={false}
            animate={{ width: advancing ? "100%" : "0%" }}
            transition={{ duration: 1.2, ease: "linear" }}
            className="absolute top-0 bottom-0 left-0 bg-[rgba(255,255,255,0.22)]"
          />
        </Link>
      </motion.div>
    </>
  );
}
