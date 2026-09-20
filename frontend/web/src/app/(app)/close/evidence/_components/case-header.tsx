"use client";

import { motion } from "motion/react";

import { CaseMetaLine } from "@/components/ui/meta-line";
import { Breadcrumb, PageTitle } from "@/components/ui/primitives";
import { transitions } from "@/lib/motion";
import { routes, withCase } from "@/lib/routes";

import { asList } from "../_data";
import { useEvidenceData } from "./data-context";

/**
 * Breadcrumb, case title and the case's meta line.
 *
 * There are no actions here. The header used to carry "View case notes" and a
 * "..." menu; the backend keeps no notes and the menu opened nothing, so both
 * are gone rather than sitting there as a promise the product cannot keep.
 */
export function CaseHeader() {
  const { data, caseParam } = useEvidenceData();
  const { CASE } = data;
  const closeHref = withCase(routes.closeCase, caseParam);

  return (
    <header>
      <Breadcrumb
        items={[
          { label: "CLOSE", href: closeHref },
          { label: "CASE STORY", href: withCase(routes.story, caseParam) },
          { label: "EVIDENCE" },
        ]}
      />

      <div className="mt-[14px]">
        {/* text-[46px] restates text-display: `cn` drops a custom font-size
            token when a text colour merges over it. */}
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
    </header>
  );
}
