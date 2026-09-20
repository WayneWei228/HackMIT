"use client";

import { motion } from "motion/react";

import {
  Breadcrumb,
  PageTitle,
  SectionLabel,
} from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import { riseIn, staggerParent, transitions } from "@/lib/motion";
import { CaseMetaLine } from "@/components/ui/meta-line";
import { chainStages, routes, withCase } from "@/lib/routes";
import { useAnalysisData } from "./data-context";
import { PulseDot } from "./glyphs";

/**
 * Case identity: where we are in the close, which vendor and period, and the
 * four numbers the whole screen is arguing about.
 */
export function CaseHeader({ pulsing }: { pulsing: boolean }) {
  const { data, agentId, agentLabel, caseParam } = useAnalysisData();
  const { caseMeta, headerStats } = data;

  /* The trail is the chain itself: the last agent that finished, then this
     one. The chain is navigation, so it comes from the route table. */
  const previous = [...chainStages(agentId, caseParam)]
    .reverse()
    .find((stage) => stage.state === "complete");

  return (
    <div className="flex-none px-[34px] pt-[26px]">
      <Breadcrumb
        items={[
          { label: "CLOSE", href: withCase(routes.closeCase, caseParam) },
          { label: "CASE STORY", href: withCase(routes.story, caseParam) },
          ...(previous
            ? [
                {
                  label: previous.name.toUpperCase(),
                  href: previous.href ?? undefined,
                },
              ]
            : []),
          { label: agentLabel.toUpperCase() },
        ]}
      />

      <div className="mt-3.5 flex items-start justify-between gap-6">
        <div className="min-w-0">
          {/* text-[46px] restates text-display: tailwind-merge reads our
              custom size tokens as colours and drops them when a primitive
              merges them against its own text colour. */}
          <PageTitle className="mt-0 text-[46px] leading-[1.02]">
            {caseMeta.vendor}
          </PageTitle>
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ ...transitions.slow, delay: 0.04 }}
            className="font-display mt-0.5 text-4xl leading-[1.1] tracking-tight text-ink-deep"
          >
            {caseMeta.period}
          </motion.div>
          <CaseMetaLine items={caseMeta.attributes} className="mt-[15px]" />
        </div>

        {/* The comp's "View case notes" and "..." actions opened screens
            that have no backend behind them, so they are not drawn: an
            affordance that leads nowhere is worse than none. */}
      </div>

      <motion.div
        variants={staggerParent(0.05)}
        initial="hidden"
        animate="visible"
        style={{
          gridTemplateColumns: `repeat(${Math.max(headerStats.length, 1)}, minmax(0, 1fr))`,
        }}
        className="mt-[26px] grid pb-[22px]"
      >
        {headerStats.map((stat, i) => (
          <motion.div
            key={stat.label}
            variants={riseIn}
            className={cn(
              i === 0 ? "pr-6" : "border-l border-line px-6",
            )}
          >
            <SectionLabel className="text-[10.5px] text-faint">
              {stat.label}
            </SectionLabel>
            {stat.kind === "amount" ? (
              <div
                className={cn(
                  "font-display mt-[9px] text-3xl leading-none",
                  stat.tone === "accent" ? "text-accent" : "text-ink-deep",
                )}
              >
                {stat.value}
              </div>
            ) : (
              <div className="mt-[9px] flex items-center gap-2.5">
                <PulseDot halo pulsing={pulsing} />
                <span className="font-display text-[24px] leading-none text-ink-deep">
                  {stat.value}
                </span>
              </div>
            )}
          </motion.div>
        ))}
      </motion.div>
    </div>
  );
}
