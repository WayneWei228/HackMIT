"use client";

import { useEffect, useState } from "react";

import { caseDetailPath, documentPath, getJson } from "./api";

/** One field the extractor pulled off a document. Nulls are dropped. */
export type DocumentRecord = Readonly<Record<string, unknown>>;

export type CaseDocument = {
  doc_id: string;
  doc_type: string;
  quality?: string;
  period?: string;
  record?: DocumentRecord | null;
};

export type DocumentDetail = CaseDocument & { text?: string | null };

/** `record` as label/value pairs, in the order the extractor emitted them. */
export function recordFields(
  record: DocumentRecord | null | undefined,
): { label: string; value: string }[] {
  if (!record || typeof record !== "object") return [];
  const fields: { label: string; value: string }[] = [];
  for (const [key, raw] of Object.entries(record)) {
    if (raw === null || raw === undefined || raw === "") continue;
    if (key === "document_type") continue;
    if (typeof raw === "object") continue;
    fields.push({ label: humanise(key), value: String(raw) });
  }
  return fields;
}

function humanise(key: string): string {
  const words = key.replace(/_/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** A document type as a person would say it: `USAGE_REPORT` -> `Usage report`. */
export function documentTypeLabel(docType: string | null | undefined): string {
  if (!docType) return "Document";
  return humanise(docType.toLowerCase());
}

/**
 * The documents this case was actually decided on.
 *
 * `GET /api/cases/{period}/{case_key}` carries them with their extracted
 * records, which is enough to draw a card; only the reader needs the full
 * text, and that is one further request per document. With no case selected
 * nothing is fetched and the caller keeps its demo artwork.
 */
export function useCaseDocuments(caseParam: string | null): {
  documents: CaseDocument[];
  loaded: boolean;
} {
  const path = caseDetailPath(caseParam);
  const [state, setState] = useState<{
    path: string | null;
    documents: CaseDocument[];
  }>({ path: null, documents: [] });

  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    let cancelled = false;

    getJson<{ documents?: CaseDocument[] }>(path, controller.signal)
      .then((payload) => {
        if (cancelled) return;
        const documents = Array.isArray(payload?.documents)
          ? payload.documents.filter((doc) => doc && doc.doc_id)
          : [];
        setState({ path, documents });
      })
      .catch(() => {
        /* The caller stays on whatever it was showing. */
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [path]);

  const current = state.path === path ? state : null;
  return { documents: current?.documents ?? [], loaded: current !== null };
}

/** One document's full text and extracted record, fetched on demand. */
export function useDocumentDetail(docId: string | null): {
  detail: DocumentDetail | null;
  loading: boolean;
} {
  const path = documentPath(docId);
  const [state, setState] = useState<{
    path: string | null;
    detail: DocumentDetail | null;
  }>({ path: null, detail: null });

  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    let cancelled = false;

    getJson<DocumentDetail>(path, controller.signal)
      .then((detail) => {
        if (cancelled) return;
        setState({ path, detail: detail?.doc_id ? detail : null });
      })
      .catch(() => {
        /* Leave the viewer on its placeholder. */
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [path]);

  const current = state.path === path ? state : null;
  return {
    detail: current?.detail ?? null,
    loading: path !== null && current === null,
  };
}
