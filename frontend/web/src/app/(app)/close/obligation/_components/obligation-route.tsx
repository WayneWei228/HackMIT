"use client";

import { StageRoute } from "@/components/close/stage-route";

import { buildObligationView } from "../_view";
import { ObligationScreen } from "./obligation-screen";
import { ObligationScreenProvider } from "./screen-context";

export function ObligationRoute() {
  return (
    <StageRoute stage="obligation">
      {(detail) => (
        <ObligationScreenProvider view={buildObligationView(detail)}>
          <ObligationScreen />
        </ObligationScreenProvider>
      )}
    </StageRoute>
  );
}
