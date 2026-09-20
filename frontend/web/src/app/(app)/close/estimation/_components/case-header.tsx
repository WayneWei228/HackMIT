"use client";

import { Fragment } from "react";

import { Breadcrumb, Button, PageTitle } from "@/components/ui/primitives";
import { MoreIcon } from "@/components/ui/icons";
import { useCaseHref } from "@/lib/case-context";
import { routes } from "@/lib/routes";
import { CaseNotesIcon } from "./icons";
import { useEstimationScreen } from "./screen-context";
import { SummaryStrip } from "./summary-strip";


/** Breadcrumb, case title, the two header actions, and the summary numbers. */
export function CaseHeader() {
  const { header } = useEstimationScreen();
  const caseHref = useCaseHref();
  const crumbs = [
    { label: "CLOSE", href: caseHref(routes.closeCase) },
    { label: "EVIDENCE", href: caseHref(routes.evidence) },
    { label: "OBLIGATION", href: caseHref(routes.obligation) },
    { label: "ESTIMATION" },
  ];
  return (
    <div className="flex-none px-[34px] pt-[26px] leading-[normal]">
      <Breadcrumb items={crumbs} />

      <div className="mt-3.5 flex items-start justify-between gap-6">
        <div className="min-w-0">
          <PageTitle className="mt-0 text-[46px] leading-[1.02]">
            {header.vendor_name}
          </PageTitle>
          <div className="font-display mt-0.5 text-4xl leading-[1.1] tracking-tight text-ink-deep">
            {header.title}
          </div>
          <div className="mt-[15px] flex flex-wrap items-center gap-x-[15px] gap-y-1 text-lead leading-[normal] text-muted-4">
            {header.chips.map((item, i) => (
              <Fragment key={item}>
                {i > 0 && (
                  <span aria-hidden="true" className="text-line-dark">
                    |
                  </span>
                )}
                <span className="whitespace-nowrap">{item}</span>
              </Fragment>
            ))}
          </div>
        </div>

        <div className="flex flex-none items-center gap-2.5 pt-1.5">
          <Button className="gap-[9px] px-3.5 py-[9px] text-[13.5px] leading-none shadow-[var(--shadow-hairline)]">
            <CaseNotesIcon className="text-muted-3" />
            View case notes
          </Button>
          <button
            type="button"
            aria-label="More case actions"
            className="flex h-9 w-[38px] cursor-pointer items-center justify-center rounded-xl border border-transparent text-muted-3 transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-wash"
          >
            <MoreIcon className="text-lead" />
          </button>
        </div>
      </div>

      <SummaryStrip />
    </div>
  );
}
