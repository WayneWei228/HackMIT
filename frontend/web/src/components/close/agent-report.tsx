import Link from "next/link";

import { JsonViewer } from "@/components/close/json-viewer";
import { NoCases } from "@/components/close/no-cases";
import { EmptyReport, ReportFrame, tokenLabel } from "@/components/reports/report-frame";
import { getCaseHandoffs, getCaseLog } from "@/lib/api";
import { caseHref } from "@/lib/case-nav";
import { loadCase, type SearchParams } from "@/lib/load-case";
import { formatMoney } from "@/lib/money";
import { routes } from "@/lib/routes";
import { agentLabel } from "@/lib/trail";

const REPORTS = {
  detection: { title: "Detection", agents: ["detection"], work: routes.closeCase },
  "invoice-lookup": { title: "Invoice lookup", agents: ["invoice_lookup"], work: routes.obligation },
  classification: { title: "Classification", agents: ["classification"], work: routes.obligation },
  outreach: { title: "Outreach", agents: ["outreach"], work: routes.verification },
  settlement: { title: "Settlement", agents: ["reconciliation", "journal_entry_service", "learning"], work: routes.verification },
} as const;

/** Label and value pairs from the case; a row the backend has no value for is left out. */
function Facts({ rows }: { rows: [string, string | null][] }) {
  return <dl className="mt-4 grid grid-cols-[160px_1fr] gap-y-2 text-sm">
    {rows.filter(([, value]) => value).map(([label, value]) => <div key={label} className="contents">
      <dt className="text-faint">{label}</dt><dd className="m-0 text-ink-2">{value}</dd>
    </div>)}
  </dl>;
}

export async function AgentReport({ stage, searchParams }: {
  stage: keyof typeof REPORTS; searchParams: SearchParams;
}) {
  const { close, detail } = await loadCase(searchParams);
  if (!detail) return <NoCases close={close} />;
  const report = REPORTS[stage];
  const id = detail.header.obligation_id;
  const [log, handoffs] = await Promise.all([getCaseLog(id), getCaseHandoffs(id)]);
  const agents: readonly string[] = report.agents;
  const entries = log?.entries.filter((entry) => agents.includes(entry.agent)) ?? [];
  const transfers = handoffs?.handoffs.filter((item) => agents.includes(item.from_agent) || agents.includes(item.to_agent)) ?? [];
  return <ReportFrame title={report.title} description={`${detail.header.vendor_name} · ${detail.header.period} · ${detail.header.status}`}
    toolbar={<div className="mt-4 flex gap-5 text-sm text-accent-deep">
      <Link className="hover:underline" href={caseHref(report.work, id)}>Open workflow controls →</Link>
      <Link className="hover:underline" href={caseHref(routes.story, id)}>Vendor story →</Link>
    </div>}>
    {stage === "detection" && <section className="mb-6 rounded-xl border border-line bg-panel p-5">
      <h2 className="font-medium">Detected obligation</h2>
      <p className="mt-2 text-sm text-muted">{id} · {detail.header.title}</p>
      <Facts rows={[
        ["Service period", detail.obligation.service_period],
        ["Opened from", detail.header.chips.join(" · ") || null],
        ["Last close accrued", detail.header.previous_accrual ? formatMoney(detail.header.previous_accrual) : null],
        ["Workflow", `${tokenLabel(detail.header.workflow_stage)} · next: ${tokenLabel(detail.header.next_action)}`],
      ]} />
    </section>}
    {stage === "invoice-lookup" && <section className="mb-6 rounded-xl border border-line bg-panel p-5">
      <h2 className="font-medium">Invoice search</h2>
      {/* A closed history month carries a result but no recorded search run, so it gets no note. */}
      {(detail.obligation.invoice_note || detail.obligation.invoice_status === "NOT_SEARCHED") && <p className="mt-2 text-sm text-muted">
        {detail.obligation.invoice_note ?? "The ledger has not been searched for this case yet."}
      </p>}
      <Facts rows={[
        ["Service period", detail.obligation.service_period],
        ["Result", tokenLabel(detail.obligation.invoice_status)],
        ["Accrual", detail.obligation.accrual_required === null ? null
          : detail.obligation.accrual_required ? "Required: no invoice was in the ledger at the close" : "Not needed: the invoice was already in the ledger"],
      ]} />
    </section>}
    {stage === "classification" && <section className="mb-6 rounded-xl border border-line bg-panel p-5">
      <h2 className="font-medium">Purchase classification</h2>
      {!detail.obligation.available ? <p className="mt-2 text-sm text-muted">This purchase has not been classified yet.</p> : <>
        <p className="mt-2 text-lg text-ink">{detail.obligation.purchase_type_label}</p>
        <p className="mt-2 text-sm text-muted">{detail.obligation.rationale}</p>
        {detail.obligation.signals.length > 0 && <table className="mt-4 w-full text-left text-sm">
          <thead className="border-b border-line text-xs text-faint"><tr><th className="pb-2">SIGNAL</th><th className="pb-2">VALUE</th><th className="pb-2">POINTS TO</th></tr></thead>
          <tbody>{detail.obligation.signals.map((signal) => <tr key={signal.name} className="border-b border-wash last:border-0">
            <td className="py-2 capitalize">{tokenLabel(signal.name)}</td>
            <td className="py-2 text-muted">{signal.value}</td>
            <td className="py-2 capitalize">{tokenLabel(signal.points_to)}</td>
          </tr>)}</tbody>
        </table>}
      </>}
    </section>}
    {stage === "settlement" && detail.verification.reconciliation && <section className="mb-6 rounded-xl border border-line bg-panel p-5">
      <h2 className="font-medium">Invoice reconciliation</h2>
      <div className="mt-3 flex gap-8 text-sm">
        <span>Accrued {formatMoney(detail.verification.reconciliation.accrued)}</span>
        <span>Actual {formatMoney(detail.verification.reconciliation.actual)}</span>
        <span>Variance {formatMoney(detail.verification.reconciliation.variance)}</span>
      </div>
      <p className="mt-3 text-sm text-muted">{detail.verification.reconciliation.explanation}</p>
    </section>}
    {stage === "outreach" && detail.outreach_threads?.map((thread) => <section key={thread.thread_id} className="mb-6 rounded-xl border border-line bg-panel p-5">
      <h2 className="font-medium">{thread.topic.replaceAll("_", " ")} · {thread.status}</h2>
      <p className="mt-1 text-xs text-faint">Simulated correspondence{thread.waiting_on ? ` · Waiting on ${thread.waiting_on.name}` : ""}</p>
      {thread.messages.map((message, index) => <article key={index} className="mt-4 border-l-2 border-accent-line pl-4">
        <p className="text-xs text-muted">{message.from.name} → {message.to.name} · {message.at}</p>
        <h3 className="mt-1 text-sm font-medium">{message.subject}</h3>
        <p className="mt-2 whitespace-pre-wrap text-sm text-muted">{message.body}</p>
      </article>)}
    </section>)}
    <h2 className="mb-3 font-medium">Recorded agent work</h2>
    {entries.length === 0 ? <EmptyReport>No {report.title.toLowerCase()} runs have been recorded for this case yet.</EmptyReport> : <div className="space-y-3">
      {entries.map((entry) => <article key={entry.seq} className="rounded-xl border border-line bg-panel p-5">
        <p className="text-xs text-faint">{agentLabel(entry.agent)} · {entry.at}</p>
        <h3 className="mt-2 font-medium">{entry.title}</h3><p className="mt-2 text-sm text-muted">{entry.summary}</p>
        <details className="mt-3"><summary className="cursor-pointer text-sm text-muted">View run JSON</summary><JsonViewer className="mt-2" value={entry} /></details>
      </article>)}
    </div>}
    <h2 className="mt-7 mb-3 font-medium">Agent handoffs</h2>
    {transfers.length === 0 ? <p className="text-sm text-faint">No handoffs recorded yet.</p> : transfers.map((item) => <details key={item.seq} className="mb-3 rounded-xl border border-line bg-panel p-4">
      <summary className="cursor-pointer text-sm">{agentLabel(item.from_agent)} → {agentLabel(item.to_agent)} · {item.payload_kind}</summary>
      <JsonViewer className="mt-3" value={item} />
    </details>)}
  </ReportFrame>;
}
