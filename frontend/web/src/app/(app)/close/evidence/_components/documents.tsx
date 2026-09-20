"use client";

import type { ReactNode } from "react";

import { SectionLabel } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import {
  documentTypeLabel,
  recordFields,
  useDocumentDetail,
} from "@/lib/use-case-documents";

/* -------------------------------------------------------------------------- */
/* Sheet                                                                       */
/* -------------------------------------------------------------------------- */

/** The paper the documents are printed on. */
function Sheet({
  className,
  children,
}: {
  className?: string;
  children?: ReactNode;
}) {
  return (
    <div
      className={cn(
        "mx-auto w-[min(700px,92%)] rounded-sm border border-sunk bg-panel shadow-[var(--shadow-pop)]",
        className,
      )}
    >
      {children}
    </div>
  );
}

const SHEET_PAD = "px-[52px] pt-[46px] pb-[58px]";
const RULE = "h-px bg-[#E4E4DC]";

/** Blank paper. What the viewer shows while a document is on its way. */
function BlankSheet() {
  return <Sheet className={cn(SHEET_PAD, "min-h-[460px]")} />;
}

/* -------------------------------------------------------------------------- */
/* A document                                                                  */
/* -------------------------------------------------------------------------- */

/**
 * One of the case's documents.
 *
 * There is no artwork here and none is invented. The API hands over the
 * record the extractor built and a plain-text rendering of the PDF, so that
 * is exactly what the sheet shows: the fields above, the page below with its
 * own whitespace preserved. The paper, the toolbar, the pager and the
 * thumbnail rail around it are the reader's chrome, which belongs to the app.
 */
export function LiveDocument({ docId }: { docId: string | null }) {
  const { detail, loading } = useDocumentDetail(docId);

  if (!detail || loading) return <BlankSheet />;

  const fields = recordFields(detail.record);
  const text = typeof detail.text === "string" ? detail.text : "";

  return (
    <Sheet className={SHEET_PAD}>
      <div className="flex items-start justify-between gap-6">
        <div className="min-w-0">
          <div className="text-[9.5px] tracking-[0.12em] text-faint-3 uppercase">
            {documentTypeLabel(detail.doc_type)}
          </div>
          <div className="font-display mt-2.5 text-[25px] break-words text-ink-deep">
            {detail.doc_id}
          </div>
        </div>
        <div className="flex-none text-right text-[9.5px] tracking-[0.12em] text-faint-3 uppercase">
          {detail.period && <div>{detail.period}</div>}
          {detail.quality && <div className="mt-1.5">{detail.quality}</div>}
        </div>
      </div>

      <div className={cn(RULE, "mt-6 mb-[26px]")} />

      {fields.length > 0 && (
        <>
          <SectionLabel className="text-[10.5px] text-faint">
            Extracted fields
          </SectionLabel>
          <div className="mt-[14px] grid grid-cols-2 gap-x-10 gap-y-[15px]">
            {fields.map((field, i) => (
              <div key={`${field.label}-${i}`} className="min-w-0">
                <div className="text-[11px] tracking-[0.06em] text-faint-3">
                  {field.label}
                </div>
                <div className="mt-[3px] text-ui break-words text-ink-2">
                  {field.value}
                </div>
              </div>
            ))}
          </div>
          <div className={cn(RULE, "mt-[30px] mb-[26px]")} />
        </>
      )}

      {text ? (
        <pre className="font-mono text-[10.5px] leading-[1.65] whitespace-pre-wrap text-ink-2">
          {text}
        </pre>
      ) : (
        <div className="text-ui text-faint-3">
          No page text was captured for this document.
        </div>
      )}
    </Sheet>
  );
}
