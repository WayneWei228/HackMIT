"use client";

import Link from "next/link";
import { motion } from "motion/react";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";
import { easeOutSoft } from "@/lib/motion";
import { routes, withCase } from "@/lib/routes";

import { CHECKLIST } from "../_data";
import { useEvidenceData } from "./data-context";
import { ChecklistTickIcon } from "./evidence-icons";

const ROW = "flex items-center gap-[14px]";
const LINK_ROW =
  "-mx-2 rounded-lg px-2 py-1.5 transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-[#F1F1EB]";

function Stage({
  index,
  label,
  status,
  barClassName,
  statusClassName,
  href,
  className,
}: {
  index: string;
  label: string;
  status: ReactNode;
  barClassName: string;
  statusClassName: string;
  href?: string;
  className?: string;
}) {
  const body = (
    <>
      <div className="w-[18px] flex-none text-meta text-faint-3 tabular-nums">
        {index}
      </div>
      <div className={cn("h-5 w-[2px] flex-none", barClassName)} />
      <div className="font-display flex-1 text-lg text-ink-deep">{label}</div>
      <div className={`text-meta ${statusClassName}`}>{status}</div>
    </>
  );

  if (href) {
    return (
      <Link href={href} className={cn(ROW, LINK_ROW, "text-ink", className)}>
        {body}
      </Link>
    );
  }

  return <div className={cn(ROW, className)}>{body}</div>;
}

/** One line of the evidence agent's working checklist. */
function ChecklistItem({
  label,
  done,
  active,
}: {
  label: string;
  done: boolean;
  active: boolean;
}) {
  const settled = done || active;

  return (
    <div className="flex items-center gap-3">
      <span className="relative mx-px h-[13px] w-[13px] flex-none">
        <motion.span
          className="absolute inset-px rounded-full border border-rule"
          initial={false}
          animate={{ opacity: settled ? 0 : 1 }}
          transition={{ duration: 0.26, ease: easeOutSoft }}
        />
        <motion.span
          className="absolute inset-px rounded-full bg-accent"
          initial={false}
          animate={{ opacity: active ? 1 : 0, scale: active ? 1 : 0.5 }}
          transition={{ duration: 0.26, ease: easeOutSoft }}
        />
        <motion.span
          className="absolute inset-0 text-accent"
          initial={false}
          animate={{ opacity: done ? 1 : 0 }}
          transition={{ duration: 0.3, ease: easeOutSoft }}
        >
          <ChecklistTickIcon />
        </motion.span>
      </span>
      <span
        className={cn(
          "text-sm transition-colors duration-[260ms] ease-[var(--ease-out-soft)]",
          settled ? "text-ink-2" : "text-faint-3",
        )}
      >
        {label}
      </span>
    </div>
  );
}

/** The agents queued behind Evidence, in chain order after the handoff. */
const QUEUED = [
  { index: "03", label: "Invoice Lookup" },
  { index: "04", label: "Classification" },
  { index: "05", label: "Estimation" },
  { index: "06", label: "Outreach" },
  { index: "07", label: "Settlement" },
];

/** The seven close stages, with the evidence checklist nested under stage 01. */
export function ExecutionSteps({
  done,
  active,
  complete,
}: {
  done: number;
  active: number;
  complete: boolean;
}) {
  const { caseParam } = useEvidenceData();

  return (
    <div className="mt-[26px]">
      <Stage
        index="01"
        label="Evidence"
        status={complete ? "Complete" : "Active"}
        barClassName="bg-accent"
        statusClassName={cn(
          "font-medium transition-colors duration-300",
          complete ? "text-faint-2" : "text-accent",
        )}
      />

      <div className="mt-[14px] ml-[33px] flex flex-col gap-[13px] border-l border-line pl-5">
        {CHECKLIST.map((label, i) => (
          <ChecklistItem
            key={`${label}-${i}`}
            label={label}
            done={i < done}
            active={i === active}
          />
        ))}
      </div>

      <Stage
        index="02"
        label="Detection"
        status={complete ? "Queued" : "Waiting"}
        barClassName={cn(
          "transition-colors duration-[400ms]",
          complete ? "bg-accent-line" : "bg-line-cool",
        )}
        statusClassName={cn(
          "transition-colors duration-300",
          complete ? "text-ink-2" : "text-faint-3",
        )}
        href={withCase(routes.detection, caseParam)}
        className="mt-[22px]"
      />

      {QUEUED.map((stage) => (
        <Stage
          key={stage.index}
          index={stage.index}
          label={stage.label}
          status="Waiting"
          barClassName="bg-line-cool"
          statusClassName="text-faint-3"
          className="mt-[22px]"
        />
      ))}
    </div>
  );
}
