import { AgentReport } from "@/components/close/agent-report";
import type { SearchParams } from "@/lib/load-case";

export const metadata = { title: "Detection - TrueUp" };

export default function Page({ searchParams }: { searchParams: SearchParams }) {
  return <AgentReport stage="detection" searchParams={searchParams} />;
}
