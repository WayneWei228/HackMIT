"use client";

import { useShownHeader } from "@/lib/stage-status";

import type { ReactNode } from "react";

import { SectionLabel } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";

import { CaseStatusValue } from "@/components/close/case-status-value";
import type { Header } from "@/lib/api-types";
import { formatMoney, formatSigned } from "@/lib/money";


function Column({
  label,
  first = false,
  children,
}: {
  label: string;
  first?: boolean;
  children: ReactNode;
}) {
  return (
    <div className={cn(first ? "pr-6" : "border-l border-line px-6")}>
      <SectionLabel className="text-[10.5px] text-faint">{label}</SectionLabel>
      {children}
    </div>
  );
}

/** The four-up figure strip under the case title. */
export function CaseStats({ header: backendHeader }: { header: Header }) {
  const header = useShownHeader(backendHeader);

  return (
    <div className="mt-[26px] grid grid-cols-4 pb-[22px]">
      <Column label="PREVIOUS ACCRUAL" first>
        <div className="font-display mt-[9px] text-3xl leading-none text-ink-deep">
          {formatMoney(header.previous_accrual)}
        </div>
      </Column>

      <Column label="SUPPORTED">
        <div className="font-display mt-[9px] text-3xl leading-none text-ink-deep">
          {formatMoney(header.supported)}
        </div>
      </Column>

      <Column label="DIFFERENCE">
        <div className="font-display mt-[9px] text-3xl leading-none text-accent">
          {formatSigned(header.difference)}
        </div>
      </Column>

      <Column label="STATUS">
        <div className="mt-[9px]">
          <CaseStatusValue status={header.status} />
        </div>
      </Column>
    </div>
  );
}
