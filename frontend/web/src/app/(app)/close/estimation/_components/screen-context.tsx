"use client";

import { createContext, useContext } from "react";
import type { ReactNode } from "react";

import { CaseProvider } from "@/lib/case-context";

import type { EstimationScreenView } from "../_view";

const ScreenContext = createContext<EstimationScreenView | null>(null);

/** Gives every panel on the Estimation screen the agent's workpaper for one case. */
export function EstimationScreenProvider({
  view,
  children,
}: {
  view: EstimationScreenView;
  children: ReactNode;
}) {
  return (
    <CaseProvider obligationId={view.obligationId} version={view.trailVersion}>
      <ScreenContext value={view}>{children}</ScreenContext>
    </CaseProvider>
  );
}

export function useEstimationScreen(): EstimationScreenView {
  const view = useContext(ScreenContext);
  if (!view) throw new Error("useEstimationScreen must be used inside EstimationScreenProvider");
  return view;
}
