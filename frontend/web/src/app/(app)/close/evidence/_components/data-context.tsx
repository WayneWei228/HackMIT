"use client";

import { createContext, useContext, useMemo, type ReactNode } from "react";

import { EMPTY, type DocTab, type EvidenceData } from "../_data";

export type EvidenceDataValue = {
  /** This case's evidence payload, as the close API served it. */
  data: EvidenceData;
  /** The `?case=` value this screen was opened with, for outgoing links. */
  caseParam: string | null;
  /**
   * The case's documents as a tab strip. Resolved once, above the tree, so
   * the strip, the viewer and the reviewed counter read the same list and
   * only one request is made for it.
   */
  tabs: readonly DocTab[];
};

/**
 * An empty payload and no documents - what a component gets when it is
 * rendered outside the provider: a story, a test, a future embed. Nothing on
 * this screen can crash for want of a provider, and nothing invents content
 * to fill the gap either.
 */
const DEFAULT: EvidenceDataValue = {
  data: EMPTY,
  caseParam: null,
  tabs: [],
};

const EvidenceDataContext = createContext<EvidenceDataValue>(DEFAULT);

/** Hands this screen's dataset to every component under it. */
export function EvidenceDataProvider({
  data,
  caseParam,
  tabs,
  children,
}: EvidenceDataValue & { children: ReactNode }) {
  const value = useMemo(
    () => ({ data, caseParam, tabs }),
    [data, caseParam, tabs],
  );
  return (
    <EvidenceDataContext.Provider value={value}>
      {children}
    </EvidenceDataContext.Provider>
  );
}

/** This screen's dataset, its documents, and the case they belong to. */
export function useEvidenceData(): EvidenceDataValue {
  return useContext(EvidenceDataContext);
}
