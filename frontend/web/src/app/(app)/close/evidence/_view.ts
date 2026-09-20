import type { Header, ObligationDetail } from "@/lib/api-types";

import { KIND_LABELS } from "../_view";

export type DocTab = {
  id: string;
  label: string;
  /** The grey suffix in the tab strip. */
  meta: string;
  kind: string;
  format: string;
  name: string;
  pages: readonly string[];
};

export type FactRow = {
  id: string;
  label: string;
  value: string;
  /** Where in the source it was read, for the tooltip. */
  citation: string;
  docId: string | null;
  page: number | null;
  /** The quoted span, shaded on the page once the fact has been revealed. */
  excerpt: string | null;
};

export type EvidenceScreenView = {
  obligationId: string;
  header: Header;
  available: boolean;
  summary: string | null;
  tabs: DocTab[];
  /** Quoted spans to highlight, by document id. */
  excerpts: Record<string, string[]>;
  facts: FactRow[];
  /** Changes whenever the case's trail grows, so it is read again. */
  trailVersion: string;
  /** The document and page holding the first quoted fact. */
  match: { docId: string; page: number } | null;
  uncertainties: string[];
};

/** Longer quotes are context, not evidence: they are not shaded on the page. */
const MAX_HIGHLIGHT_CHARS = 400;

/** Which documents to open on first, most telling first. */
const KIND_PRIORITY = ["agreement", "po", "order", "usage", "receipt", "delivery"];

/** A fact the agent extracted twice from the same place is one fact. */
function dedupe<T extends { label: string; value: string | null; file_id: string | null }>(
  facts: readonly T[],
): T[] {
  const seen = new Set<string>();
  return facts.filter((fact) => {
    const key = `${fact.label}\u0000${fact.value ?? ""}\u0000${fact.file_id ?? ""}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

/** The quoted spans to shade, by document, for just these facts. */
export function excerptsOf(facts: readonly FactRow[]): Record<string, string[]> {
  const excerpts: Record<string, string[]> = {};
  for (const fact of facts) {
    if (fact.docId && fact.excerpt && fact.excerpt.length <= MAX_HIGHLIGHT_CHARS) {
      (excerpts[fact.docId] ??= []).push(fact.excerpt);
    }
  }
  return excerpts;
}

export function buildEvidenceView(detail: ObligationDetail): EvidenceScreenView {
  const { evidence, header } = detail;
  const tabs = evidence.documents.map<DocTab>((doc) => ({
    id: doc.file_id,
    label: KIND_LABELS[doc.kind] ?? doc.kind,
    meta: `${doc.format} · ${doc.size_label}`,
    kind: doc.kind,
    format: doc.format,
    name: doc.name,
    pages: doc.pages,
  }));

  const excerpts: Record<string, string[]> = {};
  for (const fact of evidence.facts) {
    if (fact.file_id && fact.excerpt && fact.excerpt.length <= MAX_HIGHLIGHT_CHARS) {
      (excerpts[fact.file_id] ??= []).push(fact.excerpt);
    }
  }

  const facts = dedupe(evidence.facts).map<FactRow>((fact) => ({
    id: fact.evidence_id,
    label: fact.label,
    value: fact.value || fact.label,
    citation: [fact.file_name, fact.page ? `p. ${fact.page}` : null]
      .filter(Boolean)
      .join(" · "),
    docId: fact.file_id,
    page: fact.page,
    excerpt: fact.excerpt,
  }));

  const rank = (fileId: string | null) => {
    const kind = tabs.find((tab) => tab.id === fileId)?.kind ?? "";
    const index = KIND_PRIORITY.indexOf(kind);
    return index === -1 ? KIND_PRIORITY.length : index;
  };
  const first = evidence.facts
    .filter(
      (fact) =>
        fact.file_id &&
        fact.page &&
        fact.excerpt &&
        fact.excerpt.length <= MAX_HIGHLIGHT_CHARS &&
        tabs.some((tab) => tab.id === fact.file_id),
    )
    .sort((a, b) => rank(a.file_id) - rank(b.file_id))[0];

  return {
    obligationId: header.obligation_id,
    header,
    available: evidence.available,
    summary: evidence.summary,
    tabs,
    excerpts,
    facts,
    match: first ? { docId: first.file_id as string, page: first.page as number } : null,
    uncertainties: evidence.uncertainties,
    trailVersion: `${header.log_count ?? 0}:${header.handoff_count ?? 0}`,
  };
}
