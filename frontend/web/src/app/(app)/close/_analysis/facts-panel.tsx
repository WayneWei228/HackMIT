"use client";

import Link from "next/link";
import { motion } from "motion/react";

import { ChevronRightIcon } from "@/components/ui/icons";
import { transitions } from "@/lib/motion";
import { routes, safeHref, withCase } from "@/lib/routes";
import { useAnalysisData } from "./data-context";
import type { SourceFact } from "./types";
import { SourceDocIcon } from "./glyphs";
import { Panel, PanelHeading } from "./panel";

/** Facts settle in one at a time as the agent reads them. */
function factMotion(visible: boolean) {
  return {
    animate: { opacity: visible ? 1 : 0, y: visible ? 0 : 6 },
    transition: transitions.slow,
  };
}

/**
 * Left column: every fact the obligation is derived from, each one carrying
 * the document it came out of.
 */
export function FactsPanel({ step }: { step: number }) {
  const { data, caseParam } = useAnalysisData();
  const { sourceFacts, factAttributes, sourceDocumentsLabel } = data;

  return (
    <Panel className="flex flex-col px-5 pt-5 pb-4">
      <PanelHeading className="border-b border-divider-3 pb-3.5">
        Facts in scope
      </PanelHeading>

      {sourceFacts.map((fact, index) => (
        <motion.div
          key={`${fact.label}-${index}`}
          initial={false}
          {...factMotion(step >= fact.appearsAt)}
          className="border-b border-wash-deep py-4"
        >
          <div className="text-ui text-ink-2">{fact.label}</div>
          <div className="mt-[9px] flex items-start gap-[11px]">
            <SourceDocIcon className="mt-[3px] flex-none text-faint-3" />
            <div className="min-w-0">
              {/* A fact value may be an amount or a long label: it wraps inside the card, never past it. */}
              <div
                title={fact.amount}
                className={`font-display leading-[1.15] [overflow-wrap:anywhere] text-ink-deep ${fact.amount.length > 16 ? "text-[17px]" : "text-xl"}`}
              >
                {fact.amount}
              </div>
              <FactSource fact={fact} caseParam={caseParam} />
            </div>
          </div>
        </motion.div>
      ))}

      <motion.div
        initial={false}
        {...factMotion(step >= factAttributes.appearsAt)}
        className="pt-4"
      >
        {factAttributes.items.map((attribute, i) => (
          <div key={attribute.label} className={i > 0 ? "mt-[17px]" : undefined}>
            <div className="text-ui text-ink-2">{attribute.label}</div>
            <div className="font-display mt-[7px] text-lg leading-[normal] text-ink-deep">
              {attribute.value}
            </div>
          </div>
        ))}
      </motion.div>

      <div className="min-h-[18px] flex-1" />

      <Link
        href={withCase(routes.evidence, caseParam)}
        className="-mx-2.5 -mb-1 mt-3.5 flex items-center justify-between gap-2.5 rounded-b-md border-t border-wash-deep p-2.5 text-sm leading-[normal] text-muted transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-rail-alt hover:text-ink"
      >
        <span>{sourceDocumentsLabel}</span>
        <ChevronRightIcon className="text-faint-3" />
      </Link>
    </Panel>
  );
}

/**
 * The document a fact came out of.
 *
 * A live payload cites screens by whatever path the backend knows, some of
 * which this app has never had. `safeHref` returns null for those, and an
 * un-navigable citation is printed rather than linked - a dead link reads as
 * a bug, a plain citation reads as a fact.
 */
function FactSource({
  fact,
  caseParam,
}: {
  fact: SourceFact;
  caseParam: string | null;
}) {
  const href = safeHref(fact.href, caseParam);
  const className =
    "mt-[5px] inline-block text-micro text-faint-2 transition-colors duration-[160ms]";

  if (!href) return <span className={className}>{fact.source}</span>;
  return (
    <Link href={href} className={`${className} hover:text-accent-link`}>
      {fact.source}
    </Link>
  );
}
