import type { CaseStatus } from "./api-types";

/** Status dot colour, and whether the dot carries a live pulse ring. */
export const STATUS_STYLES: Record<CaseStatus, { dot: string; pulse: boolean }> = {
  Pending: { dot: "#B9BFB3", pulse: false },
  Running: { dot: "#63A644", pulse: true },
  "In progress": { dot: "#9AA096", pulse: false },
  "Needs review": { dot: "#D6A43C", pulse: false },
  Waiting: { dot: "#7C93B0", pulse: false },
  Blocked: { dot: "#C2543D", pulse: false },
  "Close-ready": { dot: "#2E8047", pulse: false },
  Complete: { dot: "#1F5132", pulse: false },
};

/** Statuses that only exist once the Policy stage has run and returned its decision. */
const AFTER_POLICY: readonly CaseStatus[] = ["Blocked", "Needs review", "Close-ready", "Complete"];

/**
 * The status to show for a case. Blocked, Needs review and Close-ready are the
 * outcome of the Policy stage, so while agents are still due to run and
 * Verification has not completed, a case reads In progress (or Pending if
 * nothing ran) whatever the row says. A case at rest keeps the status the
 * backend gave it: it may legitimately have been routed on before Policy.
 */
export function shownStatus(
  status: CaseStatus,
  stagesCompleted: readonly string[] | undefined,
  currentAgent?: string | null,
): CaseStatus {
  if (!stagesCompleted) return status;
  /* Running is what the runner shows while a call is in flight. A case waiting for the reader to run its next agent is In progress. */
  if (status === "Running") return stagesCompleted.length === 0 ? "Pending" : "In progress";
  if (!AFTER_POLICY.includes(status)) return status;
  if (stagesCompleted.includes("Verification")) return status;
  if (currentAgent === null && stagesCompleted.length > 0) return status;
  return stagesCompleted.length === 0 ? "Pending" : "In progress";
}
