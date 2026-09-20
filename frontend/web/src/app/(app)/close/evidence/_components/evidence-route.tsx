"use client";

import { StageRoute } from "@/components/close/stage-route";

import { buildEvidenceView } from "../_view";
import { EvidenceScreen } from "./evidence-screen";

export function EvidenceRoute() {
  return <StageRoute stage="evidence">{(detail) => <EvidenceScreen view={buildEvidenceView(detail)} />}</StageRoute>;
}
