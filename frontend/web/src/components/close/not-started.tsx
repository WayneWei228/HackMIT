import Link from "next/link";

import { StartCaseButton } from "@/components/close/start-case-button";
import type { CloseView, Header } from "@/lib/api-types";
import { caseHref } from "@/lib/case-nav";
import { routes } from "@/lib/routes";

/**
 * What a stage screen shows for a Pending case: nothing has run yet, so no
 * panel is drawn. Starting the case runs every agent and opens Ingestion.
 */
export function NotStarted({
  close,
  header,
  screen,
}: {
  close: CloseView;
  header: Header;
  screen: string;
}) {
  const canStart =
    close.cases.find((row) => row.obligation_id === header.obligation_id)?.can_start ?? false;

  return (
    <main className="flex min-w-[760px] flex-1 flex-col items-center justify-center gap-3 px-10">
      <div className="text-eyebrow font-medium tracking-caps-xl text-faint-2">
        {header.vendor_name.toUpperCase()} / {close.period_label.toUpperCase()}
      </div>
      <div className="font-display text-4xl text-ink-deep">Not started</div>
      <p className="max-w-[460px] text-center text-lead text-muted-4 text-pretty">
        {canStart
          ? `No agent has worked this case yet, so ${screen} has nothing to show. Starting it runs Ingestion, Evidence, Obligation, Estimation and Verification in turn, and each screen fills in.`
          : `January's invoices arrived before this case was started, so it stays Pending. Reset the demo to run it from the top.`}
      </p>
      <div className="mt-2 flex items-center gap-4">
        {canStart && (
          <StartCaseButton
            obligationId={header.obligation_id}
            goTo={caseHref(routes.closeCase, header.obligation_id)}
          />
        )}
        <Link
          href={routes.cases}
          className="text-ui text-muted-4 transition-colors duration-[160ms] hover:text-ink"
        >
          All cases
        </Link>
      </div>
    </main>
  );
}
