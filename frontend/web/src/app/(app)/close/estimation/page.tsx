import type { Metadata } from "next";

import { NoCases } from "@/components/close/no-cases";
import { NotStarted } from "@/components/close/not-started";
import { loadCase, type SearchParams } from "@/lib/load-case";

import { EstimationScreen } from "./_components/estimation-screen";
import { EstimationScreenProvider } from "./_components/screen-context";
import { buildEstimationView } from "./_view";

export const metadata: Metadata = {
  title: "Estimation - TrueUp",
  description:
    "The estimation agent building the accrual amount. All data is synthetic and every upstream system is simulated.",
};

export default async function EstimationPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const { close, detail } = await loadCase(searchParams);
  if (!detail) return <NoCases close={close} />;
  if (!detail.header.started) {
    return <NotStarted close={close} header={detail.header} screen="Estimation" />;
  }
  return (
    <EstimationScreenProvider view={buildEstimationView(detail)}>
      <EstimationScreen />
    </EstimationScreenProvider>
  );
}
