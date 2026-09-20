"use client";

import { motion } from "motion/react";

import { easeOutSoft } from "@/lib/motion";
import { DecisionBox } from "./decision-box";
import { FinalMark } from "./marks";
import { useVerificationScreen } from "./screen-context";

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
  finalStatus,
  noteTitle,
  noteBody,
}: {
  finalStatus: string;
  noteTitle: string;
  noteBody: string;
}) {
  const { amount, finalRows, journal, controller, header, reconciliation } =
    useVerificationScreen();
  const ready = header.status === "Close-ready" || header.status === "Complete";
  const settled = ready;
  const statusColor = settled ? "#2E8047" : header.status === "Blocked" ? "#A4452F" : "#B9791F";
  return (
    <section className="min-h-full rounded-xl border border-divider bg-panel p-5 shadow-[var(--shadow-tile)]">
      <div className="font-display border-b border-divider-3 pb-[14px] text-2xl text-ink-deep">
        Final case status
      </div>

      <div className="mt-[18px] text-eyebrow font-medium tracking-caps-lg text-faint">
        ACCRUAL AMOUNT
      </div>
      <div className="font-display mt-1.5 text-[44px] leading-[1.1] text-ink-deep">
        {amount}
      </div>

      <div className="mt-[18px] flex flex-col">
        <div className="flex items-center justify-between gap-[14px] border-t border-wash-deep py-3">
          <span className="text-ui text-muted-4">Status</span>
          <span className="flex items-center gap-2.5">
            <FinalMark complete={settled} tone={!ready ? statusColor : undefined} />
            <motion.span
              initial={false}
              animate={{ color: statusColor }}
              transition={{ duration: 0.35, ease: easeOutSoft }}
              className="text-ui"
            >
              {finalStatus}
            </motion.span>
          </span>
        </div>

        {finalRows.map((row) => (
          <div
            key={row.label}
            className="flex items-center justify-between gap-[14px] border-t border-wash-deep py-3"
          >
            <span className="text-ui text-muted-4">{row.label}</span>
            <span className="text-ui text-ink text-right">{row.value}</span>
          </div>
        ))}

        <div className="flex items-start justify-between gap-[14px] border-t border-wash-deep py-3">
          <span className="text-ui text-muted-4">Journal entry</span>
          <span className="grid grid-cols-[20px_auto_auto] gap-x-2.5 gap-y-1.5 text-sm text-ink text-right">
            {journal.map((line) => (
              <span key={`${line.side}-${line.account}`} className="contents">
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
        animate={{ backgroundColor: settled ? "#F1F5EC" : "#F6F6F1" }}
        transition={{ duration: 0.5, ease: easeOutSoft }}
        className="mt-5 flex items-start gap-[11px] rounded-lg px-[14px] py-[13px]"
      >
        <NoteIcon complete={settled} />
        <div className="min-w-0 flex-1">
          <motion.div
            initial={false}
            animate={{ color: settled ? "#3C5840" : "#33362F" }}
            transition={TINT}
            className="text-meta font-medium leading-[1.5]"
          >
            {noteTitle}
          </motion.div>
          <motion.div
            initial={false}
            animate={{ color: settled ? "#3C5840" : "#75796F" }}
            transition={TINT}
            className="mt-[3px] text-meta leading-[1.65] text-pretty"
          >
            {noteBody}
          </motion.div>
        </div>
      </motion.div>

      {/* After January the decision is about the invoice; Case activity draws it under that finding. */}
      {controller.in_queue && !reconciliation && <DecisionBox />}
    </section>
  );
}
