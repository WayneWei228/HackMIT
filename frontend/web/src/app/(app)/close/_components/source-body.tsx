"use client";

import { Fragment } from "react";

import {
  documentTypeLabel,
  recordFields,
  type CaseDocument,
} from "@/lib/use-case-documents";
import { cn } from "@/lib/cn";
import type { SourceId } from "../_data";

/**
 * A real document, drawn in the comp's card chrome.
 *
 * The comp had ten bespoke card bodies - a Mintlify clause, an AP ledger, a
 * Slack thread - each a drawing of one particular piece of paper. None of
 * that is the product's to hold, so one generic body renders whatever the
 * case actually has: the document's own id and type, then the fields the
 * extractor pulled off it.
 */

/**
 * Which kind of card a real document belongs on.
 *
 * The cards are keyed by source kind and the API talks in document types;
 * this is the only place the two vocabularies meet.
 */
const DOC_TYPE_SOURCE: Readonly<Record<string, SourceId>> = {
  CONTRACT: "agreement",
  AGREEMENT: "agreement",
  INVOICE: "invoice",
  USAGE_REPORT: "usage",
  PO: "po",
  PURCHASE_ORDER: "po",
  ORDER_FORM: "po",
  GL: "gl",
  GENERAL_LEDGER: "gl",
  AP: "ap",
  AP_HISTORY: "ap",
  VENDOR_MASTER: "vendor",
  CLOSE_MEMO: "prior",
  EMAIL: "email",
  SLACK: "slack",
};

export function documentSourceId(
  docType: string | null | undefined,
): SourceId | null {
  if (!docType) return null;
  return DOC_TYPE_SOURCE[docType.toUpperCase()] ?? null;
}

/** The real documents of this kind, newest period first. */
export function documentsForSource(
  id: SourceId,
  documents: readonly CaseDocument[],
): CaseDocument[] {
  return documents
    .filter((doc) => documentSourceId(doc.doc_type) === id)
    .sort((a, b) => (b.period ?? "").localeCompare(a.period ?? ""));
}

function CardTitle({
  children,
  size = "lg",
}: {
  children: React.ReactNode;
  size?: "lg" | "md";
}) {
  return (
    <div
      className={cn(
        "font-display leading-[1.15] text-ink-deep",
        size === "lg" ? "text-[15px]" : "text-[13.5px]",
      )}
    >
      {children}
    </div>
  );
}

function CardKicker({ children }: { children: React.ReactNode }) {
  return <div className="mt-1 text-[8px] tracking-caps text-ghost">{children}</div>;
}

function CardRule({ className }: { className?: string }) {
  return <div className={cn("h-px bg-divider-3", className)} />;
}

function BodyBar({ className }: { className?: string }) {
  return <div className={cn("h-[5px] rounded-[1px] bg-hover-alt", className)} />;
}

export function SourceBody({
  id,
  documents,
}: {
  id: SourceId;
  documents: readonly CaseDocument[];
}) {
  const matches = documentsForSource(id, documents);
  const doc = matches[0];

  if (!doc) {
    return (
      <>
        <CardTitle>No document</CardTitle>
        <CardKicker>Nothing of this kind on the case</CardKicker>
        <CardRule className="my-[11px]" />
        <BodyBar />
        <BodyBar className="mt-[7px] w-[62%]" />
      </>
    );
  }

  const fields = recordFields(doc.record).slice(0, 7);

  return (
    <>
      <CardTitle size="md">{doc.doc_id}</CardTitle>
      <CardKicker>
        {documentTypeLabel(doc.doc_type)}
        {matches.length > 1 ? ` · +${matches.length - 1} more` : ""}
      </CardKicker>
      {fields.length > 0 ? (
        <div className="mt-4 grid grid-cols-[1fr_auto] gap-x-2 gap-y-2.5 text-nano text-ink-3">
          {fields.map((field, i) => (
            <Fragment key={`${field.label}-${i}`}>
              <div className="text-ghost">{field.label}</div>
              <div className="text-right">{field.value}</div>
            </Fragment>
          ))}
        </div>
      ) : (
        <>
          <CardRule className="my-[11px]" />
          <BodyBar />
          <BodyBar className="mt-[7px] w-[68%]" />
        </>
      )}
    </>
  );
}
