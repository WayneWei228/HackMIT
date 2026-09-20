"use client";

import { motion } from "motion/react";

import { Tag } from "@/components/ui/primitives";
import { API_BASE_URL } from "@/lib/api";
import { cn } from "@/lib/cn";
import { rowIn } from "@/lib/motion";
import { periodLabel } from "@/lib/period";

import { DOCUMENT_GRID } from "./document-grid";
import { DocumentQuality } from "./document-quality";
import { dayLabel, tokenLabel, vendorOf, type DocumentEntry } from "../_data";

/** Where the API serves a document's own file. */
function fileHref(docId: string): string {
  return `${API_BASE_URL}/api/documents/${encodeURIComponent(docId)}/file`;
}

/**
 * One document: what it is, whose it is, when the close could first see it,
 * whether it read cleanly, and the file itself.
 *
 * The file link leaves the app - it is served by the API, not by Next - so it
 * opens in a new tab and carries `rel="noreferrer"`.
 */
export function DocumentRow({ doc }: { doc: DocumentEntry }) {
  const vendor = vendorOf(doc);

  return (
    <motion.div
      variants={rowIn}
      className={cn(
        DOCUMENT_GRID,
        "rounded-xl border-b border-wash-cool px-2.5 py-[15px] transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-[#F7F7F2]",
      )}
    >
      <div className="min-w-0">
        <div className="truncate text-nav text-ink" title={doc.doc_id}>
          {doc.doc_id}
        </div>
      </div>

      <div className="min-w-0">
        <Tag className="max-w-full truncate">{tokenLabel(doc.doc_type)}</Tag>
      </div>

      <div className="truncate text-body text-ink-2" title={vendor ?? undefined}>
        {vendor ?? <span className="text-ghost-2">Not named</span>}
      </div>

      <div className="truncate text-body text-ink-2">
        {periodLabel(doc.period)}
      </div>

      <div className="truncate text-body text-faint" title={doc.known_from}>
        {dayLabel(doc.known_from)}
      </div>

      <div className="min-w-0">
        <DocumentQuality quality={doc.quality} reasons={doc.reasons} />
      </div>

      <div className="min-w-0">
        <a
          href={fileHref(doc.doc_id)}
          target="_blank"
          rel="noreferrer"
          title={doc.file_name}
          className="block truncate text-body text-accent-link transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:text-accent-press hover:underline"
        >
          {doc.file_name}
        </a>
      </div>
    </motion.div>
  );
}
