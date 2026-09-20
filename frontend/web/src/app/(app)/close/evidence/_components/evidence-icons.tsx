import type { SVGProps } from "react";

/**
 * Glyphs that only the evidence screen uses. Geometry is traced from the comp;
 * stroke colour is the one change - these inherit `currentColor` so a Tailwind
 * text colour on the parent drives them.
 */

type Props = SVGProps<SVGSVGElement>;

const S = { stroke: "currentColor", strokeWidth: 1.1 } as const;

/** Page with two ruled lines - the "View case notes" button. */
export function CaseNotesIcon(props: Props) {
  return (
    <svg width="14" height="16" viewBox="0 0 14 16" fill="none" aria-hidden="true" {...props}>
      <path d="M2.2 1.6h6.3L11.8 5v9.4H2.2z" {...S} strokeLinejoin="round" />
      <path d="M8.5 1.6V5h3.3" {...S} strokeLinejoin="round" />
      <path d="M4.4 8.2h5.2M4.4 10.6h3.6" {...S} strokeLinecap="round" />
    </svg>
  );
}

/** Tab glyph: a signed document - a contract, amendment or order. */
export function AgreementIcon(props: Props) {
  return (
    <svg width="14" height="15" viewBox="0 0 14 15" fill="none" aria-hidden="true" {...props}>
      <path d="M2.3 1.5h6L11.7 5v8.5H2.3z" {...S} strokeLinejoin="round" />
      <path d="M8.3 1.5V5h3.4" {...S} strokeLinejoin="round" />
    </svg>
  );
}

/** Tab glyph: a tabular document - a usage or delivery report. */
export function SpreadsheetIcon(props: Props) {
  return (
    <svg width="14" height="15" viewBox="0 0 14 15" fill="none" aria-hidden="true" {...props}>
      <rect x="1.8" y="1.6" width="10.4" height="11.8" rx="1.3" {...S} />
      <path d="M1.8 5.4h10.4M5.6 5.4v8" {...S} />
    </svg>
  );
}

/** Tab glyph: a written record - an invoice or a receipt. */
export function MemoIcon(props: Props) {
  return (
    <svg width="14" height="15" viewBox="0 0 14 15" fill="none" aria-hidden="true" {...props}>
      <path d="M2.3 1.5h6L11.7 5v8.5H2.3z" {...S} strokeLinejoin="round" />
      <path d="M4.6 8h4.8M4.6 10.4h3" {...S} strokeLinecap="round" />
    </svg>
  );
}

/** Viewer toolbar: show or hide the page thumbnails. */
export function ThumbnailsIcon(props: Props) {
  return (
    <svg width="17" height="17" viewBox="0 0 18 18" fill="none" aria-hidden="true" {...props}>
      <rect x="2.4" y="3.2" width="13.2" height="11.6" rx="2" stroke="currentColor" strokeWidth={1.3} />
      <path d="M7.4 3.2v11.6" stroke="currentColor" strokeWidth={1.3} />
    </svg>
  );
}

/** Viewer toolbar: download the source document. */
export function DownloadIcon(props: Props) {
  return (
    <svg width="16" height="16" viewBox="0 0 17 17" fill="none" aria-hidden="true" {...props}>
      <path d="M8.5 2.6v8.2" stroke="currentColor" strokeWidth={1.3} strokeLinecap="round" />
      <path
        d="M5.2 7.8l3.3 3.2 3.3-3.2"
        stroke="currentColor"
        strokeWidth={1.3}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M3.2 13.6h10.6" stroke="currentColor" strokeWidth={1.3} strokeLinecap="round" />
    </svg>
  );
}

/** Viewer toolbar: focus mode - collapses the execution rail. */
export function FocusIcon(props: Props) {
  return (
    <svg width="16" height="16" viewBox="0 0 17 17" fill="none" aria-hidden="true" {...props}>
      <path
        d="M10.2 2.8h4v4M6.8 14.2h-4v-4"
        stroke="currentColor"
        strokeWidth={1.3}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M14.2 2.8L9.6 7.4M2.8 14.2l4.6-4.6" stroke="currentColor" strokeWidth={1.3} strokeLinecap="round" />
    </svg>
  );
}

/** The checklist tick - a bare stroke, no disc behind it. */
export function ChecklistTickIcon(props: Props) {
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
