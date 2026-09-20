"use client";

import { motion } from "motion/react";

import { cn } from "@/lib/cn";
import { easeOutSoft } from "@/lib/motion";
import type { AssertionView, ExtraView } from "../_data";
import { AssertionMark, DiscMark } from "./marks";

const FADE = { duration: 0.3, ease: easeOutSoft };
const TINT = { duration: 0.26, ease: easeOutSoft };

function AssertionRow({
  assertion,
  last,
}: {
  assertion: AssertionView;
  last: boolean;
}) {
  const lit = assertion.state !== "pending";
  return (
    <div
      className={cn(
        "flex items-start gap-3 py-[15px]",
        last ? "pt-[15px] pb-0" : "border-b border-wash-deep",
      )}
    >
      <AssertionMark state={assertion.state} />
      <div className="min-w-0 flex-1">
        <motion.div
          initial={false}
          animate={{ color: lit ? "#33362F" : "#9AA096" }}
          transition={TINT}
          className="text-ui leading-[1.4]"
        >
          {assertion.label}
        </motion.div>
        {assertion.plain ? (
          <div className="mt-1 text-sm text-muted-4">{assertion.value}</div>
        ) : (
          <div className="font-display mt-1 text-[17px] text-ink-deep">
            {assertion.value}
          </div>
        )}
      </div>
      <motion.span
        initial={false}
        animate={{
          opacity: assertion.tagVisible ? 1 : 0,
          color: assertion.state === "done" ? "#8E938A" : "#A8ADA3",
        }}
        transition={FADE}
        className="mt-0.5 flex-none text-micro"
      >
        {assertion.tag}
      </motion.span>
    </div>
  );
}

function ExtraRow({ extra }: { extra: ExtraView }) {
  return (
    <div className="mt-[13px] flex items-center gap-3">
      <DiscMark done={extra.done} />
      <motion.span
        initial={false}
        animate={{ color: extra.done ? "#33362F" : "#9AA096" }}
        transition={TINT}
        className="flex-1 text-ui"
      >
        {extra.label}
      </motion.span>
      <motion.span
        initial={false}
        animate={{ color: extra.done ? "#8E938A" : "#A8ADA3" }}
        transition={FADE}
        className="text-micro"
      >
        {extra.tag}
      </motion.span>
    </div>
  );
}

export function AssertionsPanel({
  assertions,
  extras,
}: {
  assertions: readonly AssertionView[];
  extras: readonly ExtraView[];
}) {
  return (
    <section className="flex min-h-full flex-col rounded-xl border border-divider bg-panel px-5 pt-5 pb-[18px] shadow-[var(--shadow-tile)]">
      <div className="font-display text-2xl text-ink-deep">Assertions</div>
      <div className="mt-1.5 border-b border-divider-3 pb-[14px] text-sm leading-[1.6] text-faint">
        Key claims to verify before close.
      </div>

      {assertions.map((assertion, i) => (
        <AssertionRow
          key={assertion.label}
          assertion={assertion}
          last={i === assertions.length - 1}
        />
      ))}

      <div className="min-h-5 flex-1" />

      <div className="mt-5 border-t border-wash-deep pt-4">
        <div className="text-sm text-muted-4">Additional checks</div>
        {extras.map((extra) => (
          <ExtraRow key={extra.label} extra={extra} />
        ))}
      </div>
    </section>
  );
}
