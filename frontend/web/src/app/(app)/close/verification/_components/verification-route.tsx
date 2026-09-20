"use client";

import { useEffect, useState } from "react";

import { StageRoute } from "@/components/close/stage-route";
import { getAudit } from "@/lib/api";
import type { AuditReport } from "@/lib/api-types";

import { buildVerificationView } from "../_view";
import { VerificationScreen } from "./verification-screen";
import { VerificationScreenProvider } from "./screen-context";

/** The Auditor's report for a case, read once its verification stage has finished. */
function useAudit(obligationId: string, ready: boolean, version: number): AuditReport | null {
  const [audit, setAudit] = useState<{ id: string; version: number; report: AuditReport | null } | null>(null);
  useEffect(() => {
    if (!ready) return;
    let cancelled = false;
    getAudit(obligationId)
      .then((report) => {
        if (!cancelled) setAudit({ id: obligationId, version, report });
      })
      .catch(() => {
        if (!cancelled) setAudit({ id: obligationId, version, report: null });
      });
    return () => {
      cancelled = true;
    };
  }, [obligationId, ready, version]);
  return audit && audit.id === obligationId ? audit.report : null;
}

export function VerificationRoute() {
  return (
    <StageRoute stage="verification">
      {(detail, close) => <Loaded detail={detail} close={close} />}
    </StageRoute>
  );
}

function Loaded({
  detail,
  close,
}: {
  detail: Parameters<typeof buildVerificationView>[0];
  close: Parameters<typeof buildVerificationView>[1];
}) {
  const done = detail.header.stages_completed?.includes("Verification") ?? false;
  const audit = useAudit(detail.header.obligation_id, done, detail.header.log_count ?? 0);
  return (
    <VerificationScreenProvider view={buildVerificationView(detail, close, audit)}>
      <VerificationScreen />
    </VerificationScreenProvider>
  );
}
