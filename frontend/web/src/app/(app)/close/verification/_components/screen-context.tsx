"use client";

import { createContext, useContext } from "react";
import type { ReactNode } from "react";

import { CaseProvider } from "@/lib/case-context";

import type { VerificationScreenView } from "../_view";

const ScreenContext = createContext<VerificationScreenView | null>(null);

/** Gives every panel on the Verification screen the recorded checks for one case. */
export function VerificationScreenProvider({
  view,
  children,
}: {
  view: VerificationScreenView;
  children: ReactNode;
}) {
  return (
    <CaseProvider obligationId={view.obligationId}>
      <ScreenContext value={view}>{children}</ScreenContext>
    </CaseProvider>
  );
}

export function useVerificationScreen(): VerificationScreenView {
  const view = useContext(ScreenContext);
  if (!view) throw new Error("useVerificationScreen must be used inside VerificationScreenProvider");
  return view;
}
