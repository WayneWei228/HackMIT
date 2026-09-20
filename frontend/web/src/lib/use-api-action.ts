"use client";

import { useCallback, useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { caseData } from "./case-data";

/**
 * Runs a backend action from the browser, then re-renders the server-fetched
 * screen so it shows what the agents did. Errors are kept for the caller to show.
 */
export function useApiAction() {
  const router = useRouter();
  const [refreshing, startTransition] = useTransition();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(
    async (action: () => Promise<unknown>): Promise<boolean> => {
      setBusy(true);
      setError(null);
      try {
        await action();
        /* The screens draw from the browser's copy of each case, so it is read again too. */
        await caseData.refreshAll();
        startTransition(() => router.refresh());
        return true;
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : String(caught));
        return false;
      } finally {
        setBusy(false);
      }
    },
    [router],
  );

  return { run, pending: busy || refreshing, error, clearError: () => setError(null) };
}
