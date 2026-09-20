import { type ClassValue, clsx } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

/*
 * tailwind-merge ships knowing Tailwind's stock scales, not ours. Left
 * unconfigured it reads `text-ui` / `text-display` as *colour* utilities, so
 * `cn("text-nav", "text-ink")` silently drops the size and the element falls
 * back to the inherited 14px. Registering the theme's own scales here is what
 * makes `cn` safe to use for size + colour in the same call.
 */
const FONT_SIZES = [
  "nano", "pico", "eyebrow", "tiny", "micro", "meta", "sm", "ui",
  "body", "nav", "lead", "md", "lg", "xl", "2xl", "3xl", "4xl", "display",
];

const TRACKING = [
  "display", "tight", "wide", "wider", "caps", "caps-lg", "caps-xl", "brand",
];

const SHADOWS = [
  "hairline", "tile", "tab", "pop", "menu", "ring", "ring-soft",
];

const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      "font-size": [{ text: FONT_SIZES }],
      tracking: [{ tracking: TRACKING }],
      shadow: [{ shadow: SHADOWS }],
    },
  },
  override: {
    // Our `--text-*` tokens carry no paired line-height (see globals.css), so a
    // font size must not evict a `leading-*` set alongside it.
    conflictingClassGroups: { "font-size": [] },
  },
});

/** Merge conditional class names, with later Tailwind utilities winning. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
