"use client";

import { StageRoute } from "@/components/close/stage-route";

import { buildCloseView } from "../_view";
import { CloseCaseScreen } from "./close-case-screen";

export function IngestionRoute() {
  return <StageRoute stage="ingestion">{(detail) => <CloseCaseScreen view={buildCloseView(detail)} />}</StageRoute>;
}
