import type { SVGProps } from "react";

import type { SourceGlyph, TabGlyph } from "../_data";

/**
 * Glyphs that exist only on the close case screen.
 *
 * The shared set in `@/components/ui/icons` covers the page, search, caret and
 * chevron marks this screen reuses; everything below is geometry that appears
 * nowhere else in the app, traced from the comp at its original stroke widths.
 */

type Props = SVGProps<SVGSVGElement>;

/** Page with two ruled lines - the "View case notes" button. */
export function NoteIcon(props: Props) {
  return (
    <svg width="14" height="16" viewBox="0 0 14 16" fill="none" aria-hidden="true" {...props}>
      <path
        d="M2.2 1.6h6.3L11.8 5v9.4H2.2z"
        stroke="currentColor"
        strokeWidth={1.1}
        strokeLinejoin="round"
      />
      <path d="M8.5 1.6V5h3.3" stroke="currentColor" strokeWidth={1.1} strokeLinejoin="round" />
      <path
        d="M4.4 8.2h5.2M4.4 10.6h3.6"
        stroke="currentColor"
        strokeWidth={1.1}
        strokeLinecap="round"
      />
    </svg>
  );
}

/** The 14x16 page mark used on source card footers (1.1 stroke, not 1.25). */
export function SourcePageIcon(props: Props) {
  return (
    <svg width="14" height="16" viewBox="0 0 14 16" fill="none" aria-hidden="true" {...props}>
      <path
        d="M2.2 1.6h6.3L11.8 5v9.4H2.2z"
        stroke="currentColor"
        strokeWidth={1.1}
        strokeLinejoin="round"
      />
      <path d="M8.5 1.6V5h3.3" stroke="currentColor" strokeWidth={1.1} strokeLinejoin="round" />
    </svg>
  );
}

/** Envelope - the email thread card. */
export function MailIcon(props: Props) {
  return (
    <svg width="15" height="16" viewBox="0 0 15 16" fill="none" aria-hidden="true" {...props}>
      <rect
        x="1.6"
        y="3.4"
        width="11.8"
        height="9"
        rx="1.3"
        stroke="currentColor"
        strokeWidth={1.1}
      />
      <path
        d="M1.9 4.4l5.6 4.1 5.6-4.1"
        stroke="currentColor"
        strokeWidth={1.1}
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Message pane - the Slack export card. */
export function ChatIcon(props: Props) {
  return (
    <svg width="14" height="16" viewBox="0 0 14 16" fill="none" aria-hidden="true" {...props}>
      <rect
        x="1.8"
        y="2.2"
        width="10.4"
        height="11.6"
        rx="1.4"
        stroke="currentColor"
        strokeWidth={1.1}
      />
      <path
        d="M4.4 6h5.2M4.4 9.4h3.4"
        stroke="currentColor"
        strokeWidth={1.1}
        strokeLinecap="round"
      />
    </svg>
  );
}

const SOURCE_GLYPHS: Record<SourceGlyph, (props: Props) => React.ReactElement> = {
  page: SourcePageIcon,
  mail: MailIcon,
  chat: ChatIcon,
};

export function SourceGlyphIcon({
  glyph,
  ...props
}: Props & { glyph: SourceGlyph }) {
  const Glyph = SOURCE_GLYPHS[glyph];
  return <Glyph {...props} />;
}

/* -------------------------------------------------------------------------- */
/* Tab glyphs                                                                  */
/* -------------------------------------------------------------------------- */

/** All sources - the only tab glyph the comp tints green rather than grey. */
function SourcesGlyph(props: Props) {
  return (
    <svg width="14" height="15" viewBox="0 0 14 15" fill="none" aria-hidden="true" {...props}>
      <rect
        x="1.6"
        y="1.4"
        width="10.8"
        height="12.2"
        rx="1.4"
        stroke="currentColor"
        strokeWidth={1.15}
      />
      <path
        d="M4.2 5.2h5.6M4.2 7.6h5.6M4.2 10h3.4"
        stroke="currentColor"
        strokeWidth={1.15}
        strokeLinecap="round"
      />
    </svg>
  );
}

function DocumentGlyph(props: Props) {
  return (
    <svg width="14" height="15" viewBox="0 0 14 15" fill="none" aria-hidden="true" {...props}>
      <path
        d="M2.3 1.5h6L11.7 5v8.5H2.3z"
        stroke="currentColor"
        strokeWidth={1.1}
        strokeLinejoin="round"
      />
      <path d="M8.3 1.5V5h3.4" stroke="currentColor" strokeWidth={1.1} strokeLinejoin="round" />
    </svg>
  );
}

function SpreadsheetGlyph(props: Props) {
  return (
    <svg width="14" height="15" viewBox="0 0 14 15" fill="none" aria-hidden="true" {...props}>
      <rect
        x="1.8"
        y="1.6"
        width="10.4"
        height="11.8"
        rx="1.3"
        stroke="currentColor"
        strokeWidth={1.1}
      />
      <path d="M1.8 5.4h10.4M5.6 5.4v8" stroke="currentColor" strokeWidth={1.1} />
    </svg>
  );
}

function MemoGlyph(props: Props) {
  return (
    <svg width="14" height="15" viewBox="0 0 14 15" fill="none" aria-hidden="true" {...props}>
      <path
        d="M2.3 1.5h6L11.7 5v8.5H2.3z"
        stroke="currentColor"
        strokeWidth={1.1}
        strokeLinejoin="round"
      />
      <path
        d="M4.6 8h4.8M4.6 10.4h3"
        stroke="currentColor"
        strokeWidth={1.1}
        strokeLinecap="round"
      />
    </svg>
  );
}

function RecordGlyph(props: Props) {
  return (
    <svg width="14" height="15" viewBox="0 0 14 15" fill="none" aria-hidden="true" {...props}>
      <rect
        x="1.8"
        y="2.4"
        width="10.4"
        height="10.2"
        rx="1.3"
        stroke="currentColor"
        strokeWidth={1.1}
      />
      <path d="M1.8 5.8h10.4" stroke="currentColor" strokeWidth={1.1} />
    </svg>
  );
}

function LedgerGlyph(props: Props) {
  return (
    <svg width="14" height="15" viewBox="0 0 14 15" fill="none" aria-hidden="true" {...props}>
      <circle cx="7" cy="7.5" r="5.4" stroke="currentColor" strokeWidth={1.1} />
      <path
        d="M7 4.4v6.2M4.6 7.5h4.8"
        stroke="currentColor"
        strokeWidth={1.1}
        strokeLinecap="round"
      />
    </svg>
  );
}

const TAB_GLYPHS: Record<TabGlyph, (props: Props) => React.ReactElement> = {
  sources: SourcesGlyph,
  document: DocumentGlyph,
  spreadsheet: SpreadsheetGlyph,
  memo: MemoGlyph,
  record: RecordGlyph,
  ledger: LedgerGlyph,
};

export function TabGlyphIcon({ glyph, ...props }: Props & { glyph: TabGlyph }) {
  const Glyph = TAB_GLYPHS[glyph];
  return <Glyph {...props} />;
}

/** The 13x13 tick drawn inside a completed checklist marker. */
export function TaskCheckIcon(props: Props) {
  return (
    <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true" {...props}>
      <path
        d="M1.8 6.8l3.2 3.1 6.2-7"
        stroke="currentColor"
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
