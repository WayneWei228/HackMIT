"use client";

import { createContext, useContext, useMemo, type ReactNode } from "react";

import { EMPTY, type EstimationData } from "../_data";

/**
 * The Estimation screen's data, read from one place.
 *
 * The screen fetches the case once and publishes the result here, so a panel
 * never has to know where its figures came from - there is only one answer,
 * the backend's. The default value is the empty dataset, which means a
 * component mounted outside the provider renders blank rather than crashing.
 */
export type EstimationDataValue = {
  data: EstimationData;
  /** The raw `?case=` value, re-attached to every link out of this screen. */
  caseParam: string | null;
};

const FALLBACK: EstimationDataValue = { data: EMPTY, caseParam: null };

const EstimationDataContext = createContext<EstimationDataValue>(FALLBACK);

export function EstimationDataProvider({
  data,
  caseParam,
  children,
}: EstimationDataValue & { children: ReactNode }) {
  const value = useMemo(() => ({ data, caseParam }), [data, caseParam]);
  return (
    <EstimationDataContext.Provider value={value}>
      {children}
    </EstimationDataContext.Provider>
  );
}

export function useEstimationData(): EstimationDataValue {
  return useContext(EstimationDataContext);
}
