import type { Metadata } from "next";

import { NoCases } from "@/components/close/no-cases";
import { NotStarted } from "@/components/close/not-started";
import { stageDone } from "@/lib/trail";
import { loadCase, type SearchParams } from "@/lib/load-case";

import { CloseCaseScreen } from "./_components/close-case-screen";
import { buildCloseView } from "./_view";

export const metadata: Metadata = {
  title: "Active case - TrueUp",
  description:
    "The ingestion agent choosing which files matter for a vendor's month-end accrual. All data is synthetic and every upstream system is simulated.",
};

/**
 * `/close` - the active close case.
 *
 * The screen owns two columns of the desktop frame (the case itself and the
 * live execution rail), so it is rendered as one client component rather than
 * split here; `AppShell` in the route group layout supplies the sidebar.
 */
export default async function CloseCasePage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const { close, detail } = await loadCase(searchParams);
  if (!detail) return <NoCases close={close} />;
  if (!stageDone(detail.header, "ingestion")) {
    return <NotStarted close={close} header={detail.header} stage="ingestion" />;
  }
  return <CloseCaseScreen view={buildCloseView(detail)} />;
}
