"use client";

import Link from "next/link";
import { useState } from "react";

import { JsonViewer } from "@/components/close/json-viewer";
import { EmptyReport, tokenLabel } from "@/components/reports/report-frame";
import { documentFileUrl as fileUrl } from "@/lib/api";
import { caseHref } from "@/lib/case-nav";
import type { DocumentRecord } from "@/lib/report-types";
import { routes } from "@/lib/routes";
import { formatStamp } from "@/lib/time";

/** What a browser can draw in place; every other format only gets the link. */
const EMBEDDABLE = new Set(["PDF", "TXT"]);

export function DocumentList({ documents }: { documents: DocumentRecord[] }) {
  const [search, setSearch] = useState("");
  const [selection, setSelection] = useState("all");
  const [viewing, setViewing] = useState<string | null>(null);
  const query = search.trim().toLowerCase();
  const visible = documents.filter((doc) =>
    `${doc.name} ${doc.vendor_name} ${doc.kind}`.toLowerCase().includes(query) &&
    (selection === "all" || (selection === "selected" ? doc.selected === true : doc.selected !== true)),
  );
  return <>
    <div className="mb-5 flex items-center gap-3">
      <input aria-label="Search documents" placeholder="Search files, vendors, or types" value={search} onChange={(event) => setSearch(event.target.value)} className="w-80 rounded-lg border border-line bg-panel px-3 py-2 text-sm" />
      <select aria-label="Filter document selection" value={selection} onChange={(event) => setSelection(event.target.value)} className="rounded-lg border border-line bg-panel px-3 py-2 text-sm">
        <option value="all">All files</option><option value="selected">Selected</option><option value="other">Not selected / awaiting review</option>
      </select>
      <span className="ml-auto text-sm text-muted">{visible.length} files</span>
    </div>
    {visible.length === 0 ? <EmptyReport>No documents match this view.</EmptyReport> : <div className="space-y-2">
      {visible.map((doc) => <details key={doc.file_id} className="rounded-xl border border-line bg-panel p-4">
        <summary className="flex cursor-pointer items-center gap-5">
          <span className="w-12 text-xs text-faint">{doc.format}</span>
          <span className="min-w-0 flex-1"><span className="block truncate font-medium">{doc.name}</span><span className="text-xs text-muted">{doc.vendor_name} · {tokenLabel(doc.kind)} · {doc.size_label}</span></span>
          <span className="w-40 text-sm text-muted">{doc.user_removed ? "Removed" : doc.selected === null ? "Awaiting selection" : doc.selected ? "Selected" : "Not selected"}</span>
          <span className="text-sm text-muted">{doc.facts.length} facts</span>
        </summary>
        <div className="mt-4 space-y-3 border-t border-line pt-4">
          <p className="text-sm text-muted">Known from {formatStamp(doc.known_from).date} · Close period {doc.period}</p>
          <div className="flex items-center gap-4 text-sm">
            {EMBEDDABLE.has(doc.format) && <button type="button" onClick={() => setViewing(viewing === doc.file_id ? null : doc.file_id)} className="cursor-pointer text-accent-deep hover:underline">{viewing === doc.file_id ? "Hide file" : "View file"}</button>}
            <a className="text-accent-deep hover:underline" href={fileUrl(doc.file_id)} target="_blank" rel="noreferrer">Open file ↗</a>
          </div>
          {viewing === doc.file_id && <iframe title={doc.name} src={fileUrl(doc.file_id)} className="h-[640px] w-full rounded-lg border border-line bg-white" />}
          {doc.reason && <p className="text-sm">{doc.reason}</p>}
          {doc.obligation_id && <Link className="inline-block text-sm text-accent-deep hover:underline" href={caseHref(routes.closeCase, doc.obligation_id)}>Open case and file selection →</Link>}
          {doc.facts.length > 0 ? <JsonViewer value={doc.facts} /> : <p className="text-sm text-faint">No extracted facts recorded for this file.</p>}
        </div>
      </details>)}
    </div>}
  </>;
}
