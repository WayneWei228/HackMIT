"use client";

import { Fragment } from "react";

import { Breadcrumb, Button, PageTitle } from "@/components/ui/primitives";
import { MoreIcon } from "@/components/ui/icons";
import { routes } from "@/lib/routes";
import { CASE } from "../_data";
import { CaseNotesIcon } from "./icons";
import { SummaryStrip } from "./summary-strip";

const CRUMBS = [
  { label: "CLOSE", href: routes.closeCase },
  { label: "EVIDENCE", href: routes.evidence },
  { label: "OBLIGATION", href: routes.obligation },
  { label: "ESTIMATION" },
];

/** Breadcrumb, case title, the two header actions, and the summary numbers. */
export function CaseHeader({ pulsing }: { pulsing: boolean }) {
  return (
    <div className="flex-none px-[34px] pt-[26px] leading-[normal]">
      <Breadcrumb items={CRUMBS} />

      <div className="mt-3.5 flex items-start justify-between gap-6">
        <div className="min-w-0">
          <PageTitle className="mt-0 text-[46px] leading-[1.02]">
            {CASE.vendor}
          </PageTitle>
          <div className="font-display mt-0.5 text-4xl leading-[1.1] tracking-tight text-ink-deep">
            {CASE.title}
          </div>
          <div className="mt-[15px] flex items-center gap-[15px] text-lead leading-[normal] text-muted-4">
            {CASE.meta.map((item, i) => (
              <Fragment key={item}>
                {i > 0 && (
                  <span aria-hidden="true" className="text-line-dark">
                    |
                  </span>
                )}
                <span>{item}</span>
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

      <SummaryStrip pulsing={pulsing} />
    </div>
  );
}
