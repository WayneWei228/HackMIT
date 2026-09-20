"use client";

import { useCaseId } from "@/lib/case-context";
import { useCaseUi } from "@/lib/case-store";

/** Jump from a figure or check on a screen to the log entry or handoff behind it. */
export function useTrailLinks() {
  const id = useCaseId();
  const [, setOpen] = useCaseUi(id, "trail.open", false);
  const [, setTab] = useCaseUi<"log" | "handoffs">(id, "trail.tab", "log");
  const [, setFilter] = useCaseUi<"all" | "verification">(id, "trail.filter", "all");
  const [entries, setEntries] = useCaseUi<number[]>(id, "trail.entries", []);
  const [handoffs, setHandoffs] = useCaseUi<number[]>(id, "handoff.open", []);

  return {
    openLogEntry(seq: number) {
      setTab("log");
      setFilter("all");
      if (!entries.includes(seq)) setEntries([...entries, seq]);
      setOpen(true);
    },
    openHandoff(seq: number) {
      setTab("handoffs");
      if (!handoffs.includes(seq)) setHandoffs([...handoffs, seq]);
      setOpen(true);
    },
  };
}
