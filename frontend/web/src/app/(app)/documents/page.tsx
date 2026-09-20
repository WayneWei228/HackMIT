import { MonthLinks, ReportFrame } from "@/components/reports/report-frame";
import { getDocuments, getPeriods } from "@/lib/api";
import type { SearchParams } from "@/lib/load-case";
import { routes } from "@/lib/routes";

import { DocumentList } from "./document-list";

export const metadata = { title: "Documents - TrueUp" };

export default async function DocumentsPage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const period = typeof params.period === "string" ? params.period : undefined;
  const [data, calendar] = await Promise.all([getDocuments(period), getPeriods()]);
  return <ReportFrame title="Documents" description="Available source files, the agent’s selection, and extracted evidence. All data is synthetic."
    toolbar={<MonthLinks months={calendar.periods} selected={period} href={routes.documents} />}>
    <DocumentList documents={data.documents} />
  </ReportFrame>;
}
