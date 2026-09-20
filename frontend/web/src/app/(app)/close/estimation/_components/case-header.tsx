"use client";

import { CaseMetaLine } from "@/components/ui/meta-line";
import { Breadcrumb, PageTitle } from "@/components/ui/primitives";
import { routes, withCase } from "@/lib/routes";
import { useEstimationData } from "./data-context";
import { SummaryStrip } from "./summary-strip";

/** The case's story, the agent that handed off, then Estimation itself. */
const CRUMBS = [
  { label: "CLOSE", href: routes.closeCase },
  { label: "CASE STORY", href: routes.story },
  { label: "CLASSIFICATION", href: routes.classification },
  { label: "ESTIMATION" },
];

/** Breadcrumb, case title, the two header actions, and the summary numbers. */
export function CaseHeader({ pulsing }: { pulsing: boolean }) {
  const { data, caseParam } = useEstimationData();
  const { CASE } = data;

  return (
    <div className="flex-none px-[34px] pt-[26px] leading-[normal]">
      <Breadcrumb
        items={CRUMBS.map((crumb) => ({
          ...crumb,
          href: crumb.href ? withCase(crumb.href, caseParam) : undefined,
        }))}
      />

      <div className="mt-3.5 flex items-start justify-between gap-6">
        <div className="min-w-0">
          <PageTitle className="mt-0 text-[46px] leading-[1.02]">
            {CASE.vendor}
          </PageTitle>
          <div className="font-display mt-0.5 text-4xl leading-[1.1] tracking-tight text-ink-deep">
            {CASE.title}
          </div>
          <CaseMetaLine items={CASE.meta} className="mt-[15px]" />
        </div>

        {/* The comp's "View case notes" and "..." actions opened screens
            that have no backend behind them, so they are not drawn: an
            affordance that leads nowhere is worse than none. */}
      </div>

      <SummaryStrip pulsing={pulsing} />
    </div>
  );
}
