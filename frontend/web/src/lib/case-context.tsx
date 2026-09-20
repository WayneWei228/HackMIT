"use client";

import { createContext, useCallback, useContext } from "react";
import type { ReactNode } from "react";

import { caseHref } from "./case-nav";
import { TrailProvider } from "./case-trail";

const CaseContext = createContext<string | null>(null);

/** Names the obligation a screen shows, so links inside it keep pointing at it. */
export function CaseProvider({
  obligationId,
  version,
  children,
}: {
  obligationId: string;
  /** Changes whenever the case's trail grows, so the trail is read again. */
  version?: string | number;
  children: ReactNode;
}) {
  return (
    <CaseContext value={obligationId}>
      <TrailProvider obligationId={obligationId} version={version}>
        {children}
      </TrailProvider>
    </CaseContext>
  );
}

/** The obligation the surrounding screen shows, or null outside a case screen. */
export function useCaseId(): string | null {
  return useContext(CaseContext);
}

/** Returns a function that turns a route into a link to the same obligation. */
export function useCaseHref(): (route: string) => string {
  const obligationId = useContext(CaseContext);
  return useCallback((route: string) => caseHref(route, obligationId), [obligationId]);
}
