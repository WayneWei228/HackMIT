"use client";

import { useSearchParams } from "next/navigation";

import { DocumentsScreen } from "./documents-screen";

/**
 * The screen, reading the month out of the URL.
 *
 * Split from the page because `useSearchParams` suspends during the static
 * prerender: the page's `Suspense` boundary renders the same screen with no
 * month, so the prerendered HTML still has content.
 */
export function DocumentsRoute() {
  const period = useSearchParams().get("period");
  return <DocumentsScreen periodParam={period} />;
}
