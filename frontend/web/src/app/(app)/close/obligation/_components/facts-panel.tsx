"use client";

import Link from "next/link";

import { ChevronRightIcon } from "@/components/ui/icons";
import { useCaseHref } from "@/lib/case-context";
import { routes } from "@/lib/routes";
import { SourceDocIcon } from "./glyphs";
import { Panel, PanelHeading } from "./panel";
import { useObligationScreen } from "./screen-context";

/**
 * Left column: every fact the obligation is derived from, each one carrying
 * the document it came out of.
 */
export function FactsPanel() {
  const { facts, attributes, sourceDocumentsLabel } = useObligationScreen();
  const caseHref = useCaseHref();
  return (
    <Panel className="flex flex-col px-5 pt-5 pb-4">
      <PanelHeading className="border-b border-divider-3 pb-3.5">
        Facts in scope
      </PanelHeading>

      {facts.length === 0 && (
        <p className="py-4 text-sm text-faint-2">No document facts were extracted for this case.</p>
      )}

      {facts.map((fact, index) => (
        <div key={`${index}-${fact.label}`} className="border-b border-wash-deep py-4">
          <div className="text-ui text-ink-2">{fact.label}</div>
          <div className="mt-[9px] flex items-start gap-[11px]">
            <SourceDocIcon className="mt-[3px] flex-none text-faint-3" />
            <div className="min-w-0 flex-1">
              <div className="font-display text-xl leading-[1.15] text-ink-deep">
                {fact.amount}
              </div>
              <Link
                href={caseHref(routes.evidence)}
                className="mt-[5px] block truncate text-micro text-faint-2 transition-colors duration-[160ms] hover:text-accent-link"
                title={fact.source}
              >
                {fact.source}
              </Link>
            </div>
          </div>
        </div>
      ))}

      <div className="pt-4">
        {attributes.map((attribute, i) => (
          <div key={attribute.label} className={i > 0 ? "mt-[17px]" : undefined}>
            <div className="text-ui text-ink-2">{attribute.label}</div>
            <div className="font-display mt-[7px] text-lg leading-[normal] text-ink-deep">
              {attribute.value}
            </div>
          </div>
        ))}
      </div>

      <div className="min-h-[18px] flex-1" />

      <Link
        href={caseHref(routes.evidence)}
        className="-mx-2.5 -mb-1 mt-3.5 flex items-center justify-between gap-2.5 rounded-b-md border-t border-wash-deep p-2.5 text-sm leading-[normal] text-muted transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-rail-alt hover:text-ink"
      >
        <span>{sourceDocumentsLabel}</span>
        <ChevronRightIcon className="text-faint-3" />
      </Link>
    </Panel>
  );
}
