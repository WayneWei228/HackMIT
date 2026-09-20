import type { SVGProps } from "react";

/**
 * Glyphs that only this screen uses. Everything with a twin in
 * `@/components/ui/icons` is imported from there instead.
 */

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

/** Page glyph with two ruled lines - the "View case notes" button. */
export function CaseNotesIcon({ size = 14, ...props }: IconProps) {
  return (
    <svg
      width={size}
      height={(size / 14) * 16}
      viewBox="0 0 14 16"
      fill="none"
      aria-hidden="true"
      {...props}
    >
      <path
        d="M2.2 1.6h6.3L11.8 5v9.4H2.2z"
        stroke="currentColor"
        strokeWidth={1.1}
        strokeLinejoin="round"
      />
      <path
        d="M8.5 1.6V5h3.3"
        stroke="currentColor"
        strokeWidth={1.1}
        strokeLinejoin="round"
      />
      <path
        d="M4.4 8.2h5.2M4.4 10.6h3.6"
        stroke="currentColor"
        strokeWidth={1.1}
        strokeLinecap="round"
      />
    </svg>
  );
}

/** Solid green disc with a white tick - a completed build step. */
export function StepDoneIcon({ size = 17, ...props }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 18 18"
      fill="none"
      aria-hidden="true"
      {...props}
    >
      <circle cx="9" cy="9" r="8.4" fill="#2E8047" />
      <path
        d="M5.4 9.2l2.6 2.6 5-5.4"
        stroke="#FFFFFF"
        strokeWidth={1.6}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Bare green tick, no disc - a finished sub-check. */
export function TickIcon({ size = 13, ...props }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 13 13"
      fill="none"
      aria-hidden="true"
      {...props}
    >
      <path
        d="M1.8 6.8l3.2 3.1 6.2-7"
        stroke="#2E8047"
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Quarter-arc spinner over a pale ring - a sub-check in flight. */
export function SpinnerIcon({ size = 13, ...props }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 13 13"
      fill="none"
      aria-hidden="true"
      {...props}
    >
      <path
        d="M6.5 1a5.5 5.5 0 0 1 5.5 5.5"
        stroke="#2E8047"
        strokeWidth={1.6}
        strokeLinecap="round"
      />
      <circle cx="6.5" cy="6.5" r="5.5" stroke="#CFE0CF" strokeWidth={1.2} />
    </svg>
  );
}

/** Solid disc with a white tick, used inline beside confirmation copy. */
export function ConfirmIcon({ size = 15, ...props }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
      {...props}
    >
      <circle cx="8" cy="8" r="7.2" fill="#2E8047" />
      <path
        d="M4.7 8.2l2.2 2.2 4.4-4.8"
        stroke="#FFFFFF"
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** The narrow page glyph the input cards and the handoff block share. */
export function InputDocIcon({ size = 15, ...props }: IconProps) {
  return (
    <svg
      width={size}
      height={(size / 14) * 16}
      viewBox="0 0 14 16"
      fill="none"
      aria-hidden="true"
      {...props}
    >
      <path
        d="M2.2 1.6h6.3L11.8 5v9.4H2.2z"
        stroke="currentColor"
        strokeWidth={1.1}
        strokeLinejoin="round"
      />
      <path
        d="M8.5 1.6V5h3.3"
        stroke="currentColor"
        strokeWidth={1.1}
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** The month grid used by the coverage-period input card. */
export function InputCalendarIcon({ size = 15, ...props }: IconProps) {
  return (
    <svg
      width={size}
      height={(size / 15) * 16}
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
      {...props}
    >
      <rect
        x="1.8"
        y="2.8"
        width="12.4"
        height="11.4"
        rx="1.6"
        stroke="currentColor"
        strokeWidth={1.1}
      />
      <path
        d="M1.8 6.2h12.4M5.2 1.6v2.4M10.8 1.6v2.4"
        stroke="currentColor"
        strokeWidth={1.1}
        strokeLinecap="round"
      />
    </svg>
  );
}

/**
 * The rail's own collapse/expand carets. The shared `CaretLeftIcon` pair draws
 * at a 1.3 stroke; these two are the comp's 1.35.
 */
export function RailExpandIcon({ size = 13, ...props }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 12 12"
      fill="none"
      aria-hidden="true"
      {...props}
    >
      <path
        d="M7.4 2.2l-3.2 3.8 3.2 3.8"
        stroke="currentColor"
        strokeWidth={1.35}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function RailCollapseIcon({ size = 13, ...props }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 12 12"
      fill="none"
      aria-hidden="true"
      {...props}
    >
      <path
        d="M4.6 2.2l3.2 3.8-3.2 3.8"
        stroke="currentColor"
        strokeWidth={1.35}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
