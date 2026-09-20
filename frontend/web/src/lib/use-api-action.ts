"use client";

import { useCallback, useState, useTransition } from "react";
import { useRouter } from "next/navigation";

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
