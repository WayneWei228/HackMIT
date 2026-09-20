import type { Escalation, Header, ObligationDetail, Preview, SourceFile } from "@/lib/api-types";
import { stageDone } from "@/lib/trail";

import type { SourceGlyph, TabGlyph } from "./_data";

/** What each kind of file is called in a tab. */
export const KIND_LABELS: Record<string, string> = {
  agreement: "Agreement",
  ap: "AP history",
  prior: "Prior close",
  vendor: "Vendor master",
  gl: "General ledger",
  invoice: "Invoice",
  po: "PO / Order form",
  email: "Email thread",
  slack: "Slack export",
  usage: "Usage report",
  receipt: "Goods receipt",
  policy: "Policy memo",
  order: "Campaign order",
  delivery: "Delivery report",
  brief: "Creative brief",
  report: "Performance report",
  packing: "Packing slip",
  register: "Asset register",
  payment: "Payment record",
};

const TAB_GLYPHS: Record<string, TabGlyph> = {
  agreement: "document",
  ap: "spreadsheet",
  prior: "memo",
  vendor: "record",
  gl: "ledger",
};

/** Only this many kinds get their own tab; the rest live under "All sources". */
const MAX_KIND_TABS = 5;

export type SourceCardData = {
  id: string;
  name: string;
  kind: string;
  kindLabel: string;
  format: string;
  detail: string;
  glyph: SourceGlyph;
  /** The Ingestion agent kept this file for the Evidence agent, and the reader did not remove it. */
  picked: boolean;
  /** The reader removed this file from the agent's selection. */
  removed: boolean;
  reason: string | null;
  preview: Preview;
};

export type SourceTabData = { id: string; label: string; glyph: TabGlyph };

export type CloseCaseView = {
  obligationId: string;
  header: Header;
  /** The agent has not judged the files yet: the cards are laid out and queued. */
  pending: boolean;
  cards: SourceCardData[];
  tabs: SourceTabData[];
  available: boolean;
  filesLoaded: number;
  judge: string | null;
  summary: string | null;
  /** Set when the reader's file selection left too little evidence to accrue. */
  escalation: Escalation | null;
  /** Changes whenever the case's trail grows, so it is read again. */
  trailVersion: string;
};

function glyphFor(file: SourceFile): SourceGlyph {
  if (file.kind === "email") return "mail";
  if (file.kind === "slack") return "chat";
  return "page";
}

/** A key that changes whenever the log or handoff list of the case grows. */
export function trailVersion(header: Header): string {
  return `${header.log_count ?? 0}:${header.handoff_count ?? 0}`;
}

/** The files as they are before the agent has judged any of them. */
function offeredFiles(detail: ObligationDetail): SourceFile[] {
  return (detail.ingestion.offered ?? []).map((file) => ({
    ...file,
    selected: false,
    user_removed: false,
    reason: null,
    preview: file.preview ?? {
      card: "skeleton",
      title: file.name,
      subtitle: file.kind,
      fields: [],
      total: null,
    },
  }));
}

export function buildCloseView(detail: ObligationDetail): CloseCaseView {
  const { ingestion, header } = detail;
  const pending = !stageDone(header, "ingestion");
  const files = ingestion.files.length > 0 && !pending ? ingestion.files : offeredFiles(detail);
  const cards = files.map<SourceCardData>((file) => ({
    id: file.file_id,
    name: file.name,
    kind: file.kind,
    kindLabel: KIND_LABELS[file.kind] ?? file.kind,
    format: file.format,
    detail: file.size_label,
    glyph: glyphFor(file),
    picked: file.selected,
    removed: file.user_removed ?? false,
    reason: file.reason,
    preview: file.preview,
  }));

  // The kinds the agent picked come first, so its choices get the tabs.
  const kinds = [...cards]
    .sort((a, b) => Number(b.picked) - Number(a.picked))
    .map((card) => card.kind)
    .filter((kind, index, all) => all.indexOf(kind) === index)
    .slice(0, MAX_KIND_TABS);

  const tabs: SourceTabData[] = [
    { id: "all", label: `All sources (${cards.length})`, glyph: "sources" },
    ...kinds.map<SourceTabData>((kind) => ({
      id: kind,
      label: `${KIND_LABELS[kind] ?? kind} (${cards.filter((c) => c.kind === kind).length})`,
      glyph: TAB_GLYPHS[kind] ?? "document",
    })),
  ];

  return {
    obligationId: header.obligation_id,
    header,
    pending,
    cards,
    tabs,
    available: ingestion.available,
    filesLoaded: pending ? cards.length : ingestion.files_loaded,
    judge: ingestion.judge,
    summary: ingestion.summary,
    escalation: detail.escalation ?? null,
    trailVersion: trailVersion(header),
  };
}
