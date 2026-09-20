import type { Metadata } from "next";

import { NoCases } from "@/components/close/no-cases";
import { NotStarted } from "@/components/close/not-started";
import { getAudit } from "@/lib/api";
import { stageDone } from "@/lib/trail";
import { loadCase, type SearchParams } from "@/lib/load-case";

import { VerificationScreen } from "./_components/verification-screen";
import { VerificationScreenProvider } from "./_components/screen-context";
import { buildVerificationView } from "./_view";

export const metadata: Metadata = {
  title: "Verification - TrueUp",
  description:
    "The policy checks and the Controller's decision on an accrual. All data is synthetic and every upstream system is simulated.",
};

export default async function VerificationPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const { close, detail } = await loadCase(searchParams);
  if (!detail) return <NoCases close={close} />;
  if (!stageDone(detail.header, "verification")) {
    return <NotStarted close={close} header={detail.header} stage="verification" />;
  }
  const audit = await getAudit(detail.header.obligation_id);
  return (
    <VerificationScreenProvider view={buildVerificationView(detail, close, audit)}>
      <VerificationScreen />
    </VerificationScreenProvider>
  );
}
