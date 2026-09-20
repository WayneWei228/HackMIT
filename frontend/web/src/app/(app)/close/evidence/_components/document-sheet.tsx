"use client";

import { motion } from "motion/react";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";
import { easeOutSoft } from "@/lib/motion";

import type { DocTab } from "../_view";

/** The paper the documents are printed on. */
function Sheet({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <div
      className={cn(
        "mx-auto w-[min(700px,92%)] rounded-sm border border-sunk bg-panel shadow-[var(--shadow-pop)]",
        className,
      )}
    >
      {children}
    </div>
  );
}

type Segment = { text: string; marked: boolean };

const escape = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/**
 * Splits a page into plain and quoted runs. An excerpt matches whatever
 * whitespace the document used, since the agent read it with line breaks
 * collapsed.
 */
export function segmentPage(text: string, excerpts: readonly string[]): Segment[] {
  const ranges: [number, number][] = [];
  for (const excerpt of excerpts) {
    const tokens = excerpt.split(/\s+/).filter(Boolean).map(escape);
    if (tokens.length === 0) continue;
    const found = new RegExp(tokens.join("\\s+"), "i").exec(text);
    if (found) ranges.push([found.index, found.index + found[0].length]);
  }
  ranges.sort((a, b) => a[0] - b[0]);
  const merged: [number, number][] = [];
  for (const range of ranges) {
    const last = merged[merged.length - 1];
    if (last && range[0] <= last[1]) last[1] = Math.max(last[1], range[1]);
    else merged.push([...range]);
  }
  const segments: Segment[] = [];
  let cursor = 0;
  for (const [start, end] of merged) {
    if (start > cursor) segments.push({ text: text.slice(cursor, start), marked: false });
    segments.push({ text: text.slice(start, end), marked: true });
    cursor = end;
  }
  if (cursor < text.length) segments.push({ text: text.slice(cursor), marked: false });
  return segments;
}

/**
 * One page of a source document, as the agent read it. Spans the agent quoted
 * as evidence are shaded green once the run has found them.
 */
export function DocumentSheet({
  tab,
  page,
  excerpts,
  highlighted,
}: {
  tab: DocTab;
  page: number;
  excerpts: readonly string[];
  highlighted: boolean;
}) {
  const text = tab.pages[page - 1] ?? "";
  const segments = segmentPage(text, excerpts);
  const hasMatch = segments.some((segment) => segment.marked);
  const tabular = tab.format === "XLSX";

  return (
    <Sheet className="px-[52px] pt-[42px] pb-[54px]">
      <div className="flex items-start justify-between gap-6">
        <div className="min-w-0">
          <div className="text-[9.5px] tracking-[0.12em] text-faint-3">
            {tab.label.toUpperCase()} &nbsp;·&nbsp; {tab.format}
          </div>
          <div className="font-display mt-2 truncate text-xl text-ink-deep">{tab.name}</div>
        </div>
        <motion.div
          className="flex flex-none items-center gap-[11px]"
          initial={false}
          animate={{ opacity: highlighted && hasMatch ? 1 : 0, x: highlighted && hasMatch ? 0 : 8 }}
          transition={{ duration: 0.34, ease: easeOutSoft }}
        >
          <div className="w-[2px] self-stretch rounded-[1px] bg-[#4F9A64]" />
          <div>
            <div className="text-[9.5px] font-semibold tracking-caps text-[#4F9A64]">
              MATCH FOUND
            </div>
            <div className="font-display mt-1 text-md text-accent">
              {tab.pages.length > 1 ? `p. ${page}` : "quoted"}
            </div>
          </div>
        </motion.div>
      </div>

      <div className="mt-6 mb-[26px] h-px bg-[#E4E4DC]" />

      <div
        className={cn(
          "whitespace-pre-wrap break-words text-pretty text-ink-2",
          tabular
            ? "text-sm leading-[2] tabular-nums"
            : "font-display text-lead leading-[1.85]",
        )}
      >
        {segments.length === 0 && <span className="text-faint-2">This page has no readable text.</span>}
        {segments.map((segment, i) => (
          <span
            key={`${i}-${segment.text.length}`}
            className={cn(
              "rounded-[3px] transition-colors duration-700 ease-[var(--ease-out-soft)]",
              segment.marked && highlighted
                ? "bg-[#E4EFD7] font-medium text-ink-deep"
                : "bg-transparent",
            )}
          >
            {segment.text}
          </span>
        ))}
      </div>
    </Sheet>
  );
}
