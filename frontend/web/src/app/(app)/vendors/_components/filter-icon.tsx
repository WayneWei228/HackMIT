import type { SVGProps } from "react";

/**
 * The three-bar filter glyph from the comp's toolbar. Not in the shared icon
 * set, so it lives with the screen that uses it.
 */
export function FilterIcon({ size = 15, ...props }: SVGProps<SVGSVGElement> & { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" aria-hidden="true" {...props}>
      <path
        d="M2.4 4.2h11.2M4.4 8h7.2M6.4 11.8h3.2"
        stroke="currentColor"
        strokeWidth={1.2}
        strokeLinecap="round"
      />
    </svg>
  );
}
