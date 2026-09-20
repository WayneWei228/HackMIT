import type { VendorView } from "@/lib/api-types";
import { formatMoney } from "@/lib/money";
import { markIndex } from "@/lib/vendor-marks";

import { MARKS, type AgentName, type MarkIndex, type Vendor } from "./_data";

const AGENT_NAMES: readonly AgentName[] = [
  "Evidence agent",
  "Obligation agent",
  "Estimation agent",
  "Verification agent",
];

export function toVendors(views: readonly VendorView[]): Vendor[] {
  return views.map((view) => ({
    name: view.name,
    id: view.vendor_id,
    obligationId: view.obligation_id,
    mark: markIndex(view.vendor_id, MARKS.length) as MarkIndex,
    initials: view.initials,
    profile: view.profile,
    treatment: view.treatment,
    workflow: view.workflow,
    amount: formatMoney(view.amount),
    sort: view.amount,
    state: view.state,
    category: view.category,
    accTreatment: view.acc_treatment,
    confidence: view.confidence,
    history: view.history.map((entry) => ({
      period: entry.period,
      amount: formatMoney(entry.amount),
      tag: entry.tag,
    })),
    sources: view.sources,
    memory: view.memory,
    relationship: view.relationship.map((entry) => ({
      when: entry.when,
      what: entry.what.replace(/\d+\.\d{2}/g, (amount) => formatMoney(amount)),
    })),
    agents: view.agents.flatMap((row) =>
      AGENT_NAMES.includes(row.label as AgentName)
        ? [{ agent: row.label as AgentName, uses: row.value }]
        : [],
    ),
  }));
}
