import type { Metadata } from "next";

import { NoCases } from "@/components/close/no-cases";
import { loadCase, type SearchParams } from "@/lib/load-case";

import { ObligationScreen } from "./_components/obligation-screen";
import { ObligationScreenProvider } from "./_components/screen-context";
import { buildObligationView } from "./_view";

export const metadata: Metadata = {
  title: "Obligation - TrueUp",
  description:
    "The obligation agent deciding what is owed for the period. All data is synthetic and every upstream system is simulated.",
};

export default async function ObligationPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const { close, detail } = await loadCase(searchParams);
  if (!detail) return <NoCases close={close} />;
  return (
    <ObligationScreenProvider view={buildObligationView(detail)}>
      <ObligationScreen />
    </ObligationScreenProvider>
  );
}
