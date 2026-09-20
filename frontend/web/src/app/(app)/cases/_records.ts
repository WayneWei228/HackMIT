import type { CaseRow } from "@/lib/api-types";
import { caseHref } from "@/lib/case-nav";
import { formatStamp } from "@/lib/time";
import { markIndex } from "@/lib/vendor-marks";
import { routes } from "@/lib/routes";

import { MARKS, type CaseCategory, type CaseRecord } from "./_data";

/** Where a case opens: the screen of the agent that has it now. */
const STAGE_ROUTE = {
  Ingestion: routes.closeCase,
  Evidence: routes.evidence,
  Obligation: routes.obligation,
  Estimation: routes.estimation,
  Verification: routes.verification,
} as const;

export function toCaseRecords(rows: readonly CaseRow[]): CaseRecord[] {
  return rows.map((row) => {
    const stamp = formatStamp(row.updated_at);
    return {
      obligationId: row.obligation_id,
      vendor: row.vendor_name,
      initials: row.initials,
      mark: markIndex(row.vendor_id, MARKS.length),
      item: row.item,
      category: row.category as CaseCategory,
      amount: row.amount,
      stage: row.stage,
      status: row.status,
      canStart: row.can_start,
      date: stamp.date,
      time: stamp.time,
      ts: stamp.ts,
      href: caseHref(STAGE_ROUTE[row.stage], row.obligation_id),
    };
  });
}
