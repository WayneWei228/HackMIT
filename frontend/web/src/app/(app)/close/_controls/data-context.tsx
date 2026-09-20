"use client";

import { createContext, useContext, useMemo, type ReactNode } from "react";

import type { ControlsData } from "./types";

type ControlsContextValue = {
  data: ControlsData;
  /** Which agent's screen this is - an `agentChain` id. */
  agentId: string;
  /** The agent's display name, from the chain. */
  agentLabel: string;
  /** `"<period>/<case_key>"`, or null when no case is selected. */
  caseParam: string | null;
};

const ControlsDataContext = createContext<ControlsContextValue | null>(null);

/**
 * One screen's dataset, shared with everything below it - the header, the
 * rail and the final-status panel all read from here rather than being
 * threaded a dozen constants through the components in between.
 */
export function ControlsDataProvider({
  data,
  agentId,
  agentLabel,
  caseParam,
  children,
}: ControlsContextValue & { children: ReactNode }) {
  const value = useMemo(
    () => ({ data, agentId, agentLabel, caseParam }),
    [data, agentId, agentLabel, caseParam],
  );
  return (
    <ControlsDataContext.Provider value={value}>
      {children}
    </ControlsDataContext.Provider>
  );
}

export function useControlsData(): ControlsContextValue {
  const value = useContext(ControlsDataContext);
  if (!value) {
    throw new Error("useControlsData must be used inside ControlsDataProvider");
  }
  return value;
}
