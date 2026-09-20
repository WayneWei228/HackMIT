"use client";

import { motion } from "motion/react";

import { MoreIcon } from "@/components/ui/icons";
import { CaseMetaLine } from "@/components/ui/meta-line";
import { Breadcrumb, Button, PageTitle } from "@/components/ui/primitives";
import { transitions } from "@/lib/motion";
import { routes, withCase } from "@/lib/routes";

import { asList } from "../_data";
import { useEvidenceData } from "./data-context";
import { CaseNotesIcon } from "./evidence-icons";

/** Breadcrumb, case title and the two header actions. */
export function CaseHeader() {
  const { data, caseParam } = useEvidenceData();
  const { CASE } = data;
  const closeHref = withCase(routes.closeCase, caseParam);

  return (
    <header>
      <Breadcrumb
        items={[
          { label: "CLOSE", href: closeHref },
          { label: "ACTIVE CASE", href: closeHref },
          { label: "EVIDENCE" },
        ]}
      />

      <div className="mt-[14px] flex items-start justify-between gap-6">
        <div className="min-w-0">
          {/* text-[46px] / text-[13.5px] restate text-display / text-ui: `cn`
              drops a custom font-size token when a text colour merges over it.
              The arbitrary size then also clears the primitive's `leading-none`,
              so the comp's `font:400 13.5px/1` has to be restated on the
              button too. */}
          <PageTitle className="mt-0 text-[46px] leading-[1.02]">
            {CASE.vendor}
          </PageTitle>

          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ ...transitions.slow, delay: 0.04 }}
            className="font-display mt-[2px] text-4xl leading-[1.1] tracking-tight text-ink-deep"
          >
            {CASE.title}
          </motion.div>

          <CaseMetaLine items={asList(CASE.meta)} className="mt-[15px]" />
        </div>

        <div className="flex flex-none items-center gap-2.5 pt-1.5">
          <Button className="gap-[9px] px-[14px] py-[9px] text-[13.5px] leading-none shadow-[var(--shadow-hairline)]">
            <CaseNotesIcon className="text-muted-3" />
            View case notes
          </Button>
          <button
            type="button"
            aria-label="More case actions"
            className="flex h-9 w-[38px] cursor-pointer items-center justify-center rounded-xl border border-transparent bg-transparent text-muted-3 transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-wash"
          >
            <MoreIcon className="text-lead" />
          </button>
        </div>
      </div>
    </header>
  );
}
