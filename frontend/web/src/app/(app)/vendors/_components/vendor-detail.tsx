"use client";

import { clsx } from "clsx";
import Link from "next/link";
import type { ReactNode } from "react";

import { CaretRightIcon, CheckCircleIcon, PageIcon } from "@/components/ui/icons";
import { cn } from "@/lib/cn";
import { caseHref } from "@/lib/case-nav";
import { AGENT_HREFS, type Vendor } from "../_data";
import { VendorMark } from "./vendor-mark";

/* -------------------------------------------------------------------------- */
/* Rail furniture                                                              */
/* -------------------------------------------------------------------------- */

/** Hairline + serif heading, the repeating rhythm of the comp's rail. */
function RailSection({
  title,
  className,
  children,
}: {
  title: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <>
      <div className={cn("mt-6 h-px bg-sunk", className)} />
      <h2 className="mt-5 font-display text-xl text-ink-deep">{title}</h2>
      {children}
    </>
  );
}

/** A dot with the 18px connector that runs down to the next entry. */
function TimelineDot({
  fill,
  ring,
  connected,
}: {
  fill?: string;
  ring?: string;
  connected: boolean;
}) {
  return (
    <span className="relative h-[9px] w-[9px]">
      <span
        className={cn("absolute inset-0 rounded-full", ring && "border-[1.4px] bg-paper")}
        style={ring ? { borderColor: ring } : { background: fill }}
      />
      {connected && (
        <span className="absolute top-[11px] left-1 h-[18px] w-px bg-[#E1E5DE]" />
      )}
    </span>
  );
}

const HISTORY_TONES = {
  Verified: { dot: "#63A644", bg: "#E3EFE2", fg: "#2C6B3C" },
  "In review": { dot: "#D6A43C", bg: "#F4EEE2", fg: "#6B5A3A" },
} as const;

/* -------------------------------------------------------------------------- */
/* Detail                                                                      */
/* -------------------------------------------------------------------------- */

export function VendorDetail({
  vendor,
  onCollapse,
}: {
  vendor: Vendor;
  onCollapse: () => void;
}) {
  const highConfidence = vendor.confidence === "High";

  return (
    <div>
      <div className="flex items-center gap-[14px]">
        <VendorMark vendor={vendor} variant="rail" />
        <div className="min-w-0 flex-1">
          <div className="truncate font-display text-[26px] leading-[1.1] text-ink-deep">
            {vendor.name}
          </div>
          <div className="mt-[3px] text-sm text-faint-2">Vendor {vendor.id}</div>
        </div>
        <button
          type="button"
          onClick={onCollapse}
          title="Collapse panel"
          aria-label="Collapse vendor detail"
          className="-mr-1 flex h-[26px] w-[26px] cursor-pointer items-center justify-center rounded-md border border-transparent text-faint-2 transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-wash-cool"
        >
          <CaretRightIcon size={13} />
        </button>
      </div>

      <RailSection title="Accounting profile" className="mt-[22px]">
        <div className="mt-[14px] grid grid-cols-[auto_1fr] items-center gap-x-4 gap-y-[13px]">
          <span className="text-ui text-muted-4">Category</span>
          <span className="text-right text-ui text-ink">{vendor.category}</span>
          <span className="text-ui text-muted-4">Treatment</span>
          <span className="text-right text-ui text-ink">{vendor.accTreatment}</span>
          <span className="text-ui text-muted-4">Confidence</span>
          <span className="text-right">
            <span
              className={clsx(
                "inline-block rounded-md px-[11px] py-[5px] text-meta",
                highConfidence
                  ? "bg-accent-soft-2 text-accent-press"
                  : "bg-[#F2EDE4] text-[#5E5140]",
              )}
            >
              {vendor.confidence}
            </span>
          </span>
        </div>
      </RailSection>

      <RailSection title="Close history">
        <div className="mt-[14px]">
          {vendor.history.map((entry, i) => {
            const tone = HISTORY_TONES[entry.tag];
            return (
              <div
                key={entry.period}
                className="relative grid grid-cols-[20px_1fr_auto_auto] items-center gap-x-3 py-[7px]"
              >
                <TimelineDot
                  fill={tone.dot}
                  connected={i < vendor.history.length - 1}
                />
                <span className="text-ui text-ink">{entry.period}</span>
                <span className="pr-3 text-ui text-ink tabular-nums">
                  {entry.amount}
                </span>
                <span
                  className="inline-block rounded-md px-2.5 py-1 text-micro"
                  style={{ background: tone.bg, color: tone.fg }}
                >
                  {entry.tag}
                </span>
              </div>
            );
          })}
        </div>
      </RailSection>

      <RailSection title="Known sources">
        <div className="mt-[14px] grid grid-cols-2 gap-x-4 gap-y-[13px]">
          {vendor.sources.map((source) => (
            <div key={source} className="flex min-w-0 items-center gap-[11px]">
              <PageIcon size={15} className="flex-none text-faint-3" />
              <span className="truncate text-ui text-ink-2">{source}</span>
            </div>
          ))}
        </div>
      </RailSection>

      <RailSection title="Agent memory">
        <div className="mt-[14px] flex items-start gap-3 rounded-xl bg-accent-tint px-[15px] py-[14px]">
          <PageIcon size={15} className="mt-[2px] flex-none text-[#5E8A62]" />
          <div className="text-sm leading-[1.7] text-pretty text-accent-slate">
            {vendor.memory}
          </div>
        </div>
      </RailSection>

      <RailSection title="Relationship history">
        <div className="mt-[14px]">
          {vendor.relationship.map((entry, i) => (
            <div
              key={`${entry.when}-${entry.what}`}
              className="grid grid-cols-[20px_104px_1fr] items-center gap-x-3 py-[7px]"
            >
              <TimelineDot
                ring={i === vendor.relationship.length - 1 ? "#BFD4C3" : "#63A644"}
                connected={i < vendor.relationship.length - 1}
              />
              <span className="text-ui text-ink">{entry.when}</span>
              <span className="text-ui text-pretty text-muted-4">{entry.what}</span>
            </div>
          ))}
        </div>
      </RailSection>

      <RailSection title="Used by agents">
        <div className="mt-[14px] flex flex-col gap-0.5">
          {vendor.agents.map((use) => (
            <Link
              key={use.agent}
              href={caseHref(AGENT_HREFS[use.agent], vendor.obligationId)}
              className="-mx-2 grid grid-cols-[18px_132px_1fr] items-center gap-x-3 rounded-md p-2 text-ink transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-[#F1F1EB] hover:text-ink"
            >
              <CheckCircleIcon size={16} className="text-accent" />
              <span className="text-ui text-ink">{use.agent}</span>
              <span className="text-ui text-muted-4">{use.uses}</span>
            </Link>
          ))}
        </div>
      </RailSection>
    </div>
  );
}
