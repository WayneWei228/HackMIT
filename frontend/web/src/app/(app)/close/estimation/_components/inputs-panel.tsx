"use client";

import Link from "next/link";

import { PendingRows } from "@/components/close/pending-rows";
import { cn } from "@/lib/cn";
import { useStagePending } from "@/lib/stage-reveal";
import { useCaseHref } from "@/lib/case-context";
import type { InputCardView } from "../_view";
import { ConfirmIcon, InputCalendarIcon, InputDocIcon } from "./icons";
import { useEstimationScreen } from "./screen-context";

/** Left column: the facts the estimate is built from, as the workpaper recorded them. */
export function InputsPanel() {
  const { inputs, footnote } = useEstimationScreen();
  const pending = useStagePending();
  return (
    <section className="flex min-h-full flex-col rounded-xl border border-divider bg-panel px-5 pt-5 pb-[18px] shadow-[var(--shadow-tile)]">
      <div className="font-display border-b border-divider-3 pb-3.5 text-2xl leading-[normal] text-ink-deep">
        Inputs
      </div>

      {pending && inputs.length === 0 && <PendingRows count={2} className="mt-5" />}
      {inputs.map((input, i) => (
        <InputCard
          key={input.label}
          input={input}
          last={i === inputs.length - 1}
        />
      ))}

      <div className="min-h-4 flex-1" />

      {footnote && (
        <div className="mt-4 flex items-start gap-2.5 rounded-lg bg-accent-tint px-[13px] py-[11px]">
          <ConfirmIcon className="mt-px flex-none" />
          <span className="min-w-0 text-meta leading-[1.5] break-words text-accent-slate">{footnote}</span>
        </div>
      )}
    </section>
  );
}

function InputCard({ input, last }: { input: InputCardView; last: boolean }) {
  const Glyph = input.icon === "calendar" ? InputCalendarIcon : InputDocIcon;
  const caseHref = useCaseHref();
  return (
    <div
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
          <div className="font-display text-xl leading-[1.15] break-words text-ink-deep">
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
    </div>
  );
}
