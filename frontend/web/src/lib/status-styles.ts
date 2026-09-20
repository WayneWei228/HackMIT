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
