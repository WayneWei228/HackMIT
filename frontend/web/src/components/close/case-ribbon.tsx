"use client";

import { Fragment } from "react";

import { CheckIcon } from "@/components/ui/icons";
import type { RibbonStep } from "@/lib/api-types";
import { useCaseId } from "@/lib/case-context";
import { useCaseData } from "@/lib/case-data";
import { cn } from "@/lib/cn";
import { formatMoney, formatSigned } from "@/lib/money";
import { formatStamp } from "@/lib/time";

const TONE = {
  NEUTRAL: { mark: "#9AA096", text: "text-ink" },
  OK: { mark: "#26503A", text: "text-accent-deep" },
  WARN: { mark: "#D6A43C", text: "text-[#8A6420]" },
  BAD: { mark: "#C2543D", text: "text-[#A4452F]" },
} as const;

function amountOf(step: RibbonStep, label: string): string | undefined {
  return step.figures.find((figure) => figure.label === label)?.amount;
}

/** The numbers a step is about, worded the way a controller would say them. */
function figureLines(step: RibbonStep): { text: string; strong?: boolean }[] {
  const lines: { text: string; strong?: boolean }[] = [];
  switch (step.key) {
    case "ACCRUAL": {
      const accrued = amountOf(step, "Accrued");
      if (accrued) lines.push({ text: formatMoney(accrued) });
      break;
    }
    case "INVOICE": {
      const corrected = amountOf(step, "Corrected");
      const first = amountOf(step, "First invoice");
      const invoiced = amountOf(step, "Invoiced");
      if (corrected && first) {
        lines.push({ text: `${formatMoney(corrected)}, was ${formatMoney(first)}` });
      } else if (invoiced) {
        lines.push({ text: formatMoney(invoiced) });
      }
      break;
    }
    case "VARIANCE": {
      const gap = amountOf(step, "Difference");
      const accrued = amountOf(step, "Accrued");
      const invoiced = amountOf(step, "Invoiced");
      if (gap) lines.push({ text: formatSigned(gap), strong: true });
      if (accrued && invoiced) {
        lines.push({ text: `${formatMoney(accrued)} vs ${formatMoney(invoiced)}` });
      }
      break;
    }
    case "LEARNING": {
      const before = amountOf(step, "Error before");
      const after = amountOf(step, "Error after");
      if (before && after) {
        lines.push({ text: `Error ${formatMoney(before)} to ${formatMoney(after)}` });
      }
      break;
    }
    default:
      break;
  }
  return lines;
}

/** Keeps a hyphenated word such as "step-up" on one line instead of splitting it across two. */
function Unbroken({ text }: { text: string }) {
  return text.split(" ").map((word, i) => (
    <Fragment key={i}>
      {i > 0 && " "}
      {word.includes("-") ? <span className="whitespace-nowrap">{word}</span> : word}
    </Fragment>
  ));
}

function whenLabel(at: string | null): string | null {
  if (!at) return null;
  const stamp = formatStamp(at);
  return at.length <= 10 ? stamp.date : `${stamp.date}, ${stamp.time}`;
}

function Mark({ step }: { step: RibbonStep }) {
  const { mark } = TONE[step.tone];
  if (step.state === "DONE") {
    return (
      <span
        className="flex h-[14px] w-[14px] flex-none items-center justify-center rounded-full text-accent-on-2 transition-colors duration-[380ms]"
        style={{ background: mark }}
      >
        <CheckIcon size={9} />
      </span>
    );
  }
  if (step.state === "CURRENT") {
    return (
      <span className="relative flex h-[14px] w-[14px] flex-none items-center justify-center">
        <span
          className="animate-pulse-ring absolute inset-0 rounded-full opacity-40"
          style={{ background: mark }}
        />
        <span
          className="relative flex h-[14px] w-[14px] items-center justify-center rounded-full border-2 bg-panel"
          style={{ borderColor: mark }}
        >
          <span className="h-[4px] w-[4px] rounded-full" style={{ background: mark }} />
        </span>
      </span>
    );
  }
  if (step.state === "SKIPPED") {
    return (
      <span className="flex h-[14px] w-[14px] flex-none items-center justify-center">
        <span
          className="h-px w-[8px] rounded-full"
          style={{ background: step.tone === "BAD" ? mark : "#B9BFB3" }}
        />
      </span>
    );
  }
  return (
    <span className="h-[14px] w-[14px] flex-none rounded-full border border-line-dark bg-panel transition-colors duration-[380ms]" />
  );
}

function Hover({ step, align }: { step: RibbonStep; align: "left" | "right" }) {
  const when = whenLabel(step.at);
  return (
    <div
      role="tooltip"
      className={cn(
        "pointer-events-none invisible absolute top-full z-30 mt-2 w-[280px] rounded-xl border border-divider bg-panel px-3.5 py-3 opacity-0 shadow-[var(--shadow-pop)] transition-opacity duration-[160ms] group-hover:visible group-hover:opacity-100 group-focus-visible:visible group-focus-visible:opacity-100",
        align === "left" ? "left-0" : "right-0",
      )}
    >
      <div className="text-eyebrow font-medium tracking-caps-lg text-faint uppercase">
        {step.label}
      </div>
      <div className={cn("mt-1 text-body leading-[1.3]", TONE[step.tone].text)}>
        <Unbroken text={step.headline} />
      </div>
      {step.detail && (
        <div className="mt-1.5 text-meta leading-[1.45] text-muted-3">{step.detail}</div>
      )}
      {step.figures.length > 0 && (
        <dl className="mt-2.5 flex flex-col gap-1 border-t border-line pt-2.5 text-meta">
          {step.figures.map((figure) => (
            <div key={figure.label} className="flex justify-between gap-3">
              <dt className="text-faint">{figure.label}</dt>
              <dd className="text-ink">
                {figure.label === "Difference"
                  ? formatSigned(figure.amount)
                  : formatMoney(figure.amount)}
              </dd>
            </div>
          ))}
        </dl>
      )}
      {when && <div className="mt-2 text-meta text-faint-2">{when}</div>}
    </div>
  );
}

function Step({ step, index, count }: { step: RibbonStep; index: number; count: number }) {
  const filled = step.state !== "UPCOMING";
  const lines = figureLines(step);
  const tone = TONE[step.tone];
  /* The basis of the accrual and the outcome of the learning are the two lines a reader needs at a glance. */
  const showDetail =
    step.detail !== "" && (step.state === "CURRENT" || step.key === "ACCRUAL" || step.key === "LEARNING");
  const wide = filled && (step.state === "CURRENT" || step.key === "LEARNING");
  return (
    <li
      tabIndex={filled ? 0 : undefined}
      className={cn(
        "group relative flex min-w-0 basis-0 flex-col pr-3 outline-none transition-[flex-grow] duration-[380ms] ease-[var(--ease-out-soft)]",
        wide
          ? "min-w-[150px] grow-[2.4]"
          : filled
            ? "min-w-[124px] grow-[1.7]"
            : "min-w-[104px] grow-[0.7]",
      )}
    >
      <div className="flex items-center gap-2">
        <Mark step={step} />
        {index < count - 1 && (
          <span
            aria-hidden="true"
            className={cn(
              "h-px flex-1 transition-colors duration-[380ms]",
              step.state === "DONE" || step.state === "SKIPPED" ? "bg-accent-line" : "bg-line-warm",
            )}
          />
        )}
      </div>
      <div
        className={cn(
          "mt-2 text-eyebrow font-medium tracking-caps uppercase",
          filled ? "text-muted-3" : "text-faint-3",
        )}
      >
        {step.label}
      </div>
      {filled && (
        <>
          <div
            className={cn(
              "mt-[3px] line-clamp-3 text-ui leading-[1.25]",
              step.state === "SKIPPED" ? "text-faint" : tone.text,
            )}
          >
            <Unbroken text={step.headline} />
          </div>
          {lines.map((line) => (
            <div
              key={line.text}
              className={cn(
                "mt-[2px] text-meta leading-[1.3]",
                line.strong ? cn("font-medium", tone.text) : "text-muted-3",
              )}
            >
              {line.text}
            </div>
          ))}
          {showDetail && (
            <div className="mt-[3px] line-clamp-3 text-meta leading-[1.35] text-muted-3">
              {step.detail}
            </div>
          )}
          <Hover step={step} align={index < count / 2 ? "left" : "right"} />
        </>
      )}
    </li>
  );
}

/**
 * The case's story over time, read from what the agents recorded: accrual posted,
 * invoice arrives, variance, diagnosis, Controller, learning. A step fills in only
 * once it has happened, and the first one still waiting is marked current.
 */
export function CaseRibbon({ className }: { className?: string }) {
  const id = useCaseId();
  const { detail } = useCaseData(id);
  const steps = detail?.ribbon;
  const filled = steps?.some((step) => step.state !== "UPCOMING") ?? false;
  return (
    <div
      className={cn(
        "flex-none pb-4 transition-[min-height] duration-[380ms] ease-[var(--ease-out-soft)]",
        filled ? "min-h-[104px]" : "min-h-[56px]",
        className ?? "px-[34px] pt-1.5",
      )}
    >
      {steps && steps.length > 0 && (
        <ol aria-label="How this case unfolds" className="flex items-start">
          {steps.map((step, index) => (
            <Step key={step.key} step={step} index={index} count={steps.length} />
          ))}
        </ol>
      )}
    </div>
  );
}
