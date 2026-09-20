"use client";

import { healthPath } from "./api";
import { useLiveData } from "./use-live-data";

export type Health = {
  status?: string;
  /** Whose books these are. The only org name the product knows. */
  company?: string;
  periods?: unknown;
};

export type Connection = {
  /** Reachable, still trying, or not answering. */
  state: "connecting" | "connected" | "offline";
  /** The company name, or null until the backend says. */
  company: string | null;
  url: string | null;
  retry: () => void;
};

/**
 * Whether the close API is there, and who it belongs to.
 *
 * This is the one request the whole app shares: the sidebar shows its result
 * as a connection dot, and the org label under it is `company` - not a name
 * this product holds anywhere of its own.
 */
export function useHealth(): Connection {
  const live = useLiveData<Health>(healthPath);
  const state =
    live.status === "ready"
      ? "connected"
      : live.status === "error"
        ? "offline"
        : "connecting";
  return {
    state,
    company: live.data?.company ?? null,
    url: live.url,
    retry: live.retry,
  };
}
