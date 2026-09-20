"use client";

import type { ReactNode } from "react";

import { CaseRunnerProvider } from "@/lib/case-runner";
import { CaseStoreProvider } from "@/lib/case-store";

/**
 * Client state that has to outlive navigation between screens: what the browser
 * remembers per case, and the runner that drives an in-flight close one stage
 * at a time. Mounted once at the (app) layout.
 */
export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <CaseStoreProvider>
      <CaseRunnerProvider>{children}</CaseRunnerProvider>
    </CaseStoreProvider>
  );
}
