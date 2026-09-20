"use client";

import Link from "next/link";
import { motion } from "motion/react";

import { cn } from "@/lib/cn";
import { timing } from "../_motion";
import { useCaseHref } from "@/lib/case-context";
import { INPUTS_FOOTNOTE_AT } from "../_data";
import type { InputCardView } from "../_view";
import { ConfirmIcon, InputCalendarIcon, InputDocIcon } from "./icons";
import { useEstimationScreen } from "./screen-context";

/** Left column: the facts the estimate is built from, revealed as they load. */
export function InputsPanel({ step }: { step: number }) {
  const { inputs, footnote } = useEstimationScreen();
  return (
    <section className="flex min-h-full flex-col rounded-xl border border-divider bg-panel px-5 pt-5 pb-[18px] shadow-[var(--shadow-tile)]">
      <div className="font-display border-b border-divider-3 pb-3.5 text-2xl leading-[normal] text-ink-deep">
        Inputs
      </div>

      {inputs.map((input, i) => (
        <InputCard
          key={input.label}
          input={input}
          shown={step >= input.revealAt}
          last={i === inputs.length - 1}
        />
      ))}

      <div className="min-h-4 flex-1" />

      <motion.div
        animate={{
          opacity: step >= INPUTS_FOOTNOTE_AT ? 1 : 0,
          y: step >= INPUTS_FOOTNOTE_AT ? 0 : 6,
        }}
        transition={timing.settle}
        className="mt-4 flex items-center gap-2.5 rounded-lg bg-accent-tint px-[13px] py-[11px]"
      >
        <ConfirmIcon />
        <span className="text-meta leading-[normal] text-accent-slate">{footnote}</span>
      </motion.div>
    </section>
  );
}

function InputCard({
  input,
  shown,
  last,
}: {
  input: InputCardView;
  shown: boolean;
  last: boolean;
}) {
  const Glyph = input.icon === "calendar" ? InputCalendarIcon : InputDocIcon;
  const caseHref = useCaseHref();
  return (
    <motion.div
      animate={{ opacity: shown ? 1 : 0, y: shown ? 0 : 6 }}
      transition={timing.fact}
      className={cn(
        "py-4",
        last ? "pt-4 pb-0" : "border-b border-wash-deep",
      )}
    >
      <div
        className="text-ui leading-[normal] text-ink-2"
      >
        {input.label}
      </div>
      <div className="mt-[9px] flex items-start gap-[11px]">
        <Glyph className="mt-[3px] flex-none text-faint-3" />
        <div className="min-w-0 leading-[normal]">
          <div className="font-display text-xl leading-[1.15] text-ink-deep">
            {input.value}
          </div>
          {input.sub &&
            (input.linkTo ? (
              <Link
                href={caseHref(input.linkTo)}
                className="mt-[5px] inline-block text-micro leading-[normal] text-faint-2 transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:text-accent-link"
              >
                {input.sub}
              </Link>
            ) : (
              <div className="mt-[5px] text-micro leading-[normal] text-faint-2">{input.sub}</div>
            ))}
        </div>
      </div>
    </motion.div>
  );
}
