"use client";

import { createContext, useContext, useMemo, type ReactNode } from "react";

import type { AnalysisData } from "./types";

type AnalysisContextValue = {
  data: AnalysisData;
  /** Which agent's screen this is - an `agentChain` id. */
  agentId: string;
  /** The agent's display name, from the chain. */
  agentLabel: string;
  /** `"<period>/<case_key>"`, or null when no case is selected. */
  caseParam: string | null;
};

const AnalysisDataContext = createContext<AnalysisContextValue | null>(null);

/**
 * One screen's data, shared with everything below it.
 *
 * The panels sit three and four levels down inside the rail and the check
 * list; threading a dozen fields through as props would mean touching every
 * component in between for every new field, so the screen publishes the
 * payload once and the leaves read what they need.
 */
export function AnalysisDataProvider({
  data,
  agentId,
  agentLabel,
  caseParam,
  children,
}: AnalysisContextValue & { children: ReactNode }) {
  const value = useMemo(
    () => ({ data, agentId, agentLabel, caseParam }),
    [data, agentId, agentLabel, caseParam],
  );
  return (
    <AnalysisDataContext.Provider value={value}>
      {children}
    </AnalysisDataContext.Provider>
  );
}

export function useAnalysisData(): AnalysisContextValue {
  const value = useContext(AnalysisDataContext);
  if (!value) {
    throw new Error("useAnalysisData must be used inside AnalysisDataProvider");
  }
  return value;
}
