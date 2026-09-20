"use client";

import { useSearchParams } from "next/navigation";

import { CasesScreen } from "./cases-screen";

/**
 * The screen, reading the month out of the URL.
 *
 * Split from the page because `useSearchParams` suspends during the static
 * prerender: the page's `Suspense` boundary renders the same screen with no
 * month, so the prerendered HTML still has content.
 */
export function CasesRoute() {
  const period = useSearchParams().get("period");
  return <CasesScreen periodParam={period} />;
}
