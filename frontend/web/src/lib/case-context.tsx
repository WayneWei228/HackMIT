"use client";

import { createContext, useCallback, useContext } from "react";
import type { ReactNode } from "react";

import { caseHref } from "./case-nav";

const CaseContext = createContext<string | null>(null);

/** Names the obligation a screen shows, so links inside it keep pointing at it. */
export function CaseProvider({
  obligationId,
  children,
}: {
  obligationId: string;
  children: ReactNode;
}) {
  return <CaseContext value={obligationId}>{children}</CaseContext>;
}

/** Returns a function that turns a route into a link to the same obligation. */
export function useCaseHref(): (route: string) => string {
  const obligationId = useContext(CaseContext);
  return useCallback((route: string) => caseHref(route, obligationId), [obligationId]);
}
