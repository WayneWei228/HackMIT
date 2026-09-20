import type { Metadata } from "next";

import { NoCases } from "@/components/close/no-cases";
import { NotStarted } from "@/components/close/not-started";
import { stageDone } from "@/lib/trail";
import { loadCase, type SearchParams } from "@/lib/load-case";

import { EvidenceScreen } from "./_components/evidence-screen";
import { buildEvidenceView } from "./_view";

export const metadata: Metadata = {
  title: "Evidence - TrueUp",
  description:
    "The evidence agent reading the documents ingestion kept. All data is synthetic and every upstream system is simulated.",
};

export default async function EvidencePage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const { close, detail } = await loadCase(searchParams);
  if (!detail) return <NoCases close={close} />;
  if (!stageDone(detail.header, "evidence")) {
    return <NotStarted close={close} detail={detail} stage="evidence" />;
  }
  return <EvidenceScreen view={buildEvidenceView(detail)} />;
}
