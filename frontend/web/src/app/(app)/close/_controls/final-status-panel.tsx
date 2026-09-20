"use client";

import { motion } from "motion/react";

import { cn } from "@/lib/cn";
import { Button } from "@/components/ui/primitives";
import { easeOutSoft } from "@/lib/motion";
import { useControlsData } from "./data-context";
import { FinalMark } from "./marks";

const SETTLE = { duration: 0.45, ease: easeOutSoft };
const TINT = { duration: 0.4, ease: easeOutSoft };

function NoteIcon({ complete }: { complete: boolean }) {
  return (
    <span className="relative mt-px h-[15px] w-[15px] flex-none">
      <motion.span
        aria-hidden="true"
        initial={false}
        animate={{ opacity: complete ? 0 : 1 }}
        transition={{ duration: 0.35, ease: easeOutSoft }}
        className="absolute inset-0 block"
      >
        <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
          <circle cx="8" cy="8" r="7.2" fill="#8A9A86" />
          <path d="M8 7.2v4" stroke="#FFFFFF" strokeWidth={1.5} strokeLinecap="round" />
          <circle cx="8" cy="4.9" r=".95" fill="#FFFFFF" />
        </svg>
      </motion.span>
      <motion.span
        aria-hidden="true"
        initial={false}
        animate={{ opacity: complete ? 1 : 0 }}
        transition={{ duration: 0.35, ease: easeOutSoft }}
        className="absolute inset-0 block"
      >
        <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
          <circle cx="8" cy="8" r="7.2" fill="#2E8047" />
          <path
            d="M4.7 8.2l2.2 2.2 4.4-4.8"
            stroke="#FFFFFF"
            strokeWidth={1.5}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </motion.span>
    </span>
  );
}

export function FinalStatusPanel({
  complete,
  finalStatus,
  noteTitle,
  noteBody,
}: {
  complete: boolean;
  finalStatus: string;
  noteTitle: string;
  noteBody: string;
}) {
  const { data } = useControlsData();
  const { ACCRUAL_AMOUNT, FINAL_ROWS, JOURNAL_LINES } = data;

  return (
    <section className="min-h-full rounded-xl border border-divider bg-panel p-5 shadow-[var(--shadow-tile)]">
      <div className="font-display border-b border-divider-3 pb-[14px] text-2xl text-ink-deep">
        Final case status
      </div>

      <div className="mt-[18px] text-eyebrow font-medium tracking-caps-lg text-faint">
        ACCRUAL AMOUNT
      </div>
      <div className="font-display mt-1.5 text-[44px] leading-[1.1] text-ink-deep">
        {ACCRUAL_AMOUNT}
      </div>

      <div className="mt-[18px] flex flex-col">
        <div className="flex items-center justify-between gap-[14px] border-t border-wash-deep py-3">
          <span className="text-ui text-muted-4">Status</span>
          <span className="flex items-center gap-2.5">
            <FinalMark complete={complete} />
            <motion.span
              initial={false}
              animate={{ color: complete ? "#2E8047" : "#1D1F1B" }}
              transition={{ duration: 0.35, ease: easeOutSoft }}
              className="text-ui"
            >
              {finalStatus}
            </motion.span>
          </span>
        </div>

        {FINAL_ROWS.map((row, i) => (
          <div
            key={`${row.label}-${i}`}
            className="flex items-center justify-between gap-[14px] border-t border-wash-deep py-3"
          >
            <span className="text-ui text-muted-4">{row.label}</span>
            <span className="text-ui text-ink text-right">{row.value}</span>
          </div>
        ))}

        <div className="flex items-start justify-between gap-[14px] border-t border-wash-deep py-3">
          <span className="text-ui text-muted-4">Journal entry</span>
          <span className="grid grid-cols-[20px_auto_auto] gap-x-2.5 gap-y-1.5 text-sm text-ink text-right">
            {JOURNAL_LINES.map((line, i) => (
              <span key={`${line.side}-${line.account}-${i}`} className="contents">
                <span className="text-faint-2 text-left">{line.side}</span>
                <span>{line.account}</span>
                <span className="tabular-nums">{line.amount}</span>
              </span>
            ))}
          </span>
        </div>
      </div>

      <motion.div
        initial={false}
        animate={{ backgroundColor: complete ? "#F1F5EC" : "#F6F6F1" }}
        transition={{ duration: 0.5, ease: easeOutSoft }}
        className="mt-5 flex items-start gap-[11px] rounded-lg px-[14px] py-[13px]"
      >
        <NoteIcon complete={complete} />
        <div className="min-w-0 flex-1">
          <motion.div
            initial={false}
            animate={{ color: complete ? "#3C5840" : "#33362F" }}
            transition={TINT}
            className="text-meta font-medium leading-[1.5]"
          >
            {noteTitle}
          </motion.div>
          <motion.div
            initial={false}
            animate={{ color: complete ? "#3C5840" : "#75796F" }}
            transition={TINT}
            className="mt-[3px] text-meta leading-[1.65] text-pretty"
          >
            {noteBody}
          </motion.div>
        </div>
      </motion.div>

      <motion.div
        initial={false}
        animate={{ opacity: complete ? 1 : 0, y: complete ? 0 : 8 }}
        transition={SETTLE}
        className={cn(
          "mt-[18px] flex flex-col gap-2",
          !complete && "pointer-events-none",
        )}
      >
        {/* text-[13.5px]: `cn` reads the custom `text-ui` token as a colour and
            drops it against the variant's own text colour. Restating the size in
            turn drops `leading-none`, so both come back here. */}
        <Button
          variant="solid"
          className="w-full justify-center border border-accent px-3.5 text-[13.5px] leading-none hover:bg-accent-deep"
        >
          Approve and post journal
        </Button>
        <Button
          variant="secondary"
          className="w-full justify-center px-3.5 text-[13.5px] leading-none"
        >
          Request changes
        </Button>
      </motion.div>
    </section>
  );
}
