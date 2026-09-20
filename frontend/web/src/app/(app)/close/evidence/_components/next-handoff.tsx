"use client";

import Link from "next/link";

import { InlineHandoff } from "@/components/close/case-trail-panel";
import { PageIcon } from "@/components/ui/icons";
import type { Header } from "@/lib/api-types";
import { useNextStageOpen } from "@/lib/stage-status";
import { SectionLabel } from "@/components/ui/primitives";
import { useCaseHref } from "@/lib/case-context";
import { routes } from "@/lib/routes";

import { RAIL } from "../_data";

/** The handoff to the obligation agent: the JSON it received and the link that opens its screen. */
export function NextHandoff({ header }: { header: Header }) {
  const caseHref = useCaseHref();
  const nextOpen = useNextStageOpen(header, "evidence");

  return (
    <>
      <div className="mt-[30px] h-px bg-sunk" />
      <SectionLabel className="mt-[22px] text-[10.5px] text-faint">
        {RAIL.handoffLabel}
      </SectionLabel>

      {nextOpen && (
      <div className="mt-[13px] flex items-center gap-3">
        <PageIcon size={15} className="flex-none text-faint-3" />
        <span className="text-body text-ink">{RAIL.handoffFrom}</span>
        <span className="text-sm text-ghost-2" aria-hidden="true">
          →
        </span>
        <span className="text-body text-ink">{RAIL.handoffTo}</span>
      </div>
      )}

      <InlineHandoff screen="evidence" />

      {nextOpen && (
      <div className="mt-4">
        <Link
          href={caseHref(routes.obligation)}
          className="relative block w-full overflow-hidden rounded-xl border border-accent bg-accent px-[14px] py-[11px] text-center text-accent-on transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-accent-deep hover:text-accent-on"
        >
          <span className="relative z-[2] text-ui font-medium">{RAIL.ctaIdle}</span>
        </Link>
      </div>
      )}
    </>
  );
}
