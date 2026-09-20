"use client";

import { Suspense, type ReactNode } from "react";

import { NoCases } from "@/components/close/no-cases";
import type { CloseView, ObligationDetail } from "@/lib/api-types";
import type { StageKey } from "@/lib/case-store";
import { useStageRoute } from "@/lib/use-stage-route";

/**
 * Every stage screen goes through here. It renders the screen's real layout from
 * the browser's copy of the case as soon as the route opens, so there is never a
 * placeholder page between screens; only a browser that has read nothing yet
 * (a reload) shows the bare frame for the moment the first read takes.
 */
export function StageRoute({
  stage,
  children,
}: {
  stage: StageKey;
  children: (detail: ObligationDetail, close: CloseView) => ReactNode;
}) {
  return (
    <Suspense fallback={<StageFrame />}>
      <Inner stage={stage}>{children}</Inner>
    </Suspense>
  );
}

function Inner({
  stage,
  children,
}: {
  stage: StageKey;
  children: (detail: ObligationDetail, close: CloseView) => ReactNode;
}) {
  const { close, detail, error } = useStageRoute(stage);
  /* The nearest error boundary says the backend is not running. */
  if (error && !detail) throw error;
  if (close && close.cases.length === 0) return <NoCases close={close} />;
  if (!detail || !close) return <StageFrame />;
  return <>{children(detail, close)}</>;
}

/** The empty frame of a stage screen: the shape of the header and the panels, and nothing else. */
function StageFrame() {
  return (
    <main aria-busy="true" className="flex min-w-[760px] flex-1 flex-col overflow-hidden">
      <div className="flex-none px-[34px] pt-[26px]">
        <div className="h-[13px] w-[180px] rounded-sm bg-wash" />
        <div className="mt-4 h-[34px] w-[320px] rounded-md bg-wash" />
        <div className="mt-6 h-[44px] w-full max-w-[720px] rounded-lg bg-wash" />
      </div>
      <div className="mt-5 h-px flex-none bg-line" />
      <div className="grid flex-1 grid-cols-3 gap-3.5 px-[34px] pt-5">
        <div className="h-[220px] rounded-xl bg-wash" />
        <div className="h-[220px] rounded-xl bg-wash" />
        <div className="h-[220px] rounded-xl bg-wash" />
      </div>
    </main>
  );
}
