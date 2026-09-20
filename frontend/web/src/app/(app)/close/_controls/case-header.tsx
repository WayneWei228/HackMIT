"use client";

import { motion } from "motion/react";

import { Breadcrumb } from "@/components/ui/primitives";
import { CaseMetaLine } from "@/components/ui/meta-line";
import { chainStages, routes, withCase } from "@/lib/routes";
import { riseIn, staggerParent, transitions } from "@/lib/motion";
import { useControlsData } from "./data-context";
import { LiveDot } from "./marks";

export function CaseHeader({
  headStatus,
  pulse,
}: {
  headStatus: string;
  pulse: boolean;
}) {
  const { data, agentId, agentLabel, caseParam } = useControlsData();
  const { CASE_META, HEAD_STATS } = data;

  /* The trail: the case's story, the last agent that handed off, then this
     one. The chain is navigation, so it comes from the route table. */
  const breadcrumb = [
    { label: "CLOSE", href: withCase(routes.closeCase, caseParam) },
    { label: "CASE STORY", href: withCase(routes.story, caseParam) },
    ...chainStages(agentId, caseParam)
      .filter((stage) => stage.state === "complete")
      .slice(-1)
      .map((stage) => ({
        label: stage.name.toUpperCase(),
        href: stage.href ?? undefined,
      })),
    { label: agentLabel.toUpperCase() },
  ];

  return (
    <div className="flex-none px-[34px] pt-[26px]">
      <Breadcrumb items={breadcrumb} />

      <div className="mt-[14px] flex items-start justify-between gap-6">
        <div className="min-w-0">
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={transitions.slow}
            className="font-display text-display leading-[1.02] tracking-display text-ink-deep"
          >
            {CASE_META.vendor}
          </motion.div>
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ ...transitions.slow, delay: 0.05 }}
            className="font-display mt-0.5 text-4xl leading-[1.1] tracking-tight text-ink-deep"
          >
            {CASE_META.title}
          </motion.div>
          <CaseMetaLine items={CASE_META.facts} className="mt-[15px]" />
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
          gridTemplateColumns: `repeat(${HEAD_STATS.length + 1}, minmax(0, 1fr))`,
        }}
        className="mt-[26px] grid pb-[22px]"
      >
        {HEAD_STATS.map((stat, i) => (
          <motion.div
            key={`${stat.label}-${i}`}
            variants={riseIn}
            className={
              i === 0 ? "pr-6" : "border-l border-line px-6"
            }
          >
            <div className="text-eyebrow font-medium tracking-caps-lg text-faint">
              {stat.label}
            </div>
            <div
              className={`font-display mt-[9px] text-3xl leading-none ${
                stat.accent ? "text-accent" : "text-ink-deep"
              }`}
            >
              {stat.value}
            </div>
          </motion.div>
        ))}
        <motion.div variants={riseIn} className="border-l border-line px-6">
          <div className="text-eyebrow font-medium tracking-caps-lg text-faint">
            STATUS
          </div>
          <div className="mt-[9px] flex items-center gap-2.5">
            <LiveDot pulse={pulse} />
            <span className="font-display text-[24px] leading-none text-ink-deep">
              {headStatus}
            </span>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}
