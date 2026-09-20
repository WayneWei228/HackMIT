"use client";

import { createContext, useContext } from "react";
import type { ReactNode } from "react";

import { CaseProvider } from "@/lib/case-context";

import type { ObligationScreenView } from "../_view";

const ScreenContext = createContext<ObligationScreenView | null>(null);

/** Gives every panel on the Obligation screen the agent's findings for one case. */
export function ObligationScreenProvider({
  view,
  children,
}: {
  view: ObligationScreenView;
  children: ReactNode;
}) {
  return (
    <CaseProvider obligationId={view.obligationId}>
      <ScreenContext value={view}>{children}</ScreenContext>
    </CaseProvider>
  );
}

export function useObligationScreen(): ObligationScreenView {
  const view = useContext(ScreenContext);
  if (!view) throw new Error("useObligationScreen must be used inside ObligationScreenProvider");
  return view;
}
