"use client";

import { StageRoute } from "@/components/close/stage-route";

import { buildEstimationView } from "../_view";
import { EstimationScreen } from "./estimation-screen";
import { EstimationScreenProvider } from "./screen-context";

export function EstimationRoute() {
  return (
    <StageRoute stage="estimation">
      {(detail) => (
        <EstimationScreenProvider view={buildEstimationView(detail)}>
          <EstimationScreen />
        </EstimationScreenProvider>
      )}
    </StageRoute>
  );
}
