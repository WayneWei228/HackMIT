import Link from "next/link";

import { EmptyReport, MonthLinks, ReportFrame, tokenLabel } from "@/components/reports/report-frame";
import { getJournals, getPeriods } from "@/lib/api";
import { caseHref } from "@/lib/case-nav";
import type { SearchParams } from "@/lib/load-case";
import { formatMoney } from "@/lib/money";
import { routes } from "@/lib/routes";

export const metadata = { title: "Journals - TrueUp" };

export default async function JournalsPage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const period = typeof params.period === "string" ? params.period : undefined;
  const [data, calendar] = await Promise.all([getJournals(period), getPeriods()]);
  return (
    <ReportFrame title="Journals" description={data.note} toolbar={
      <MonthLinks months={calendar.periods} selected={period} href={routes.journals} />
    }>
      <p className="mb-4 text-sm text-muted">{data.journals.length} posted entries</p>
      {data.journals.length === 0 ? <EmptyReport>No posted journal entries for this month.</EmptyReport> : (
        <div className="space-y-4">
          {data.journals.map((entry) => (
            <article key={entry.entry_id} className="rounded-xl border border-line bg-panel p-5">
              <div className="mb-4 flex items-start justify-between gap-6">
                <div>
                  <h2 className="font-medium text-ink">{entry.vendor_name ?? "General ledger"} · <span className="capitalize">{tokenLabel(entry.entry_type)}</span>
                    {/* Still this month's entry; next month's reversal has since undone it. */}
                    {entry.status === "REVERSED" && <span className="ml-2 rounded-md border border-line px-1.5 py-0.5 text-xs font-normal text-muted">Reversed next month</span>}
                  </h2>
                  <p className="mt-1 text-sm text-muted">{entry.description}</p>
                  <p className="mt-1 font-mono text-xs text-faint">{entry.entry_id} · {entry.posting_date} · {entry.period}</p>
                </div>
                {entry.obligation_id && <Link className="shrink-0 text-sm text-accent-deep hover:underline" href={caseHref(routes.story, entry.obligation_id)}>View story →</Link>}
              </div>
              <table className="w-full text-left text-sm">
                <thead className="border-b border-line text-xs text-faint"><tr><th className="pb-2">ACCOUNT</th><th className="pb-2 text-right">DEBIT</th><th className="pb-2 text-right">CREDIT</th></tr></thead>
                <tbody>{entry.lines.map((line, index) => <tr key={index} className="border-b border-wash last:border-0">
                  <td className="py-2">{line.account} <span className="text-muted">{line.account_name}</span></td>
                  <td className="py-2 text-right tabular-nums">{line.side === "Dr" ? formatMoney(line.amount) : "—"}</td>
                  <td className="py-2 text-right tabular-nums">{line.side === "Cr" ? formatMoney(line.amount) : "—"}</td>
                </tr>)}</tbody>
              </table>
            </article>
          ))}
        </div>
      )}
    </ReportFrame>
  );
}
