"use client";

import { createContext, useContext, useMemo, type ReactNode } from "react";

import { EMPTY, type IngestionData } from "../_data";

type IngestionContextValue = {
  data: IngestionData;
  /** `"<period>/<case_key>"`, or null when no case is selected. */
  caseParam: string | null;
};

const IngestionDataContext = createContext<IngestionContextValue>({
  data: EMPTY,
  caseParam: null,
});

/**
 * The intake screen's dataset, shared with everything below it.
 *
 * The nine source cards sit three levels down inside the grid and each reads
 * its own slice of the dataset, so the screen publishes it once rather than
 * threading a dozen constants through `SourceGrid` and `SourceCard`.
 */
export function IngestionDataProvider({
  data,
  caseParam,
  children,
}: IngestionContextValue & { children: ReactNode }) {
  const value = useMemo(() => ({ data, caseParam }), [data, caseParam]);
  return (
    <IngestionDataContext.Provider value={value}>
      {children}
    </IngestionDataContext.Provider>
  );
}

/** Falls back to the empty shape rather than throwing. */
export function useIngestionData(): IngestionContextValue {
  return useContext(IngestionDataContext);
}
