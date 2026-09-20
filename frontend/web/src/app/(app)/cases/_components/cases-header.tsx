import {
  Breadcrumb,
  PageSubtitle,
  PageTitle,
} from "@/components/ui/primitives";
import { routes } from "@/lib/routes";
import { ALL_PERIODS, infoLabel, periodLabel, type PeriodInfo } from "@/lib/period";
import type { RunControls } from "@/lib/use-run-controls";

import { RunStrip } from "./run-strip";

/**
 * Page title block: where you are, which month this list is, what can be run
 * for it, and how to add to it.
 *
 * The subtitle names the selected month rather than a fixed one - no screen
 * in this product knows what month it is.
 */
export function CasesHeader({
  period,
  info,
  canClose,
  canSettle,
  controls,
  showRunStrip,
}: {
  /** The selected month, `ALL_PERIODS`, or `null` before one is resolved. */
  period: string | null;
  info: PeriodInfo | null;
  canClose: boolean;
  canSettle: boolean;
  controls: RunControls;
  /** False while the backend is unreachable - there is nothing to run then. */
  showRunStrip: boolean;
}) {
  const scoped = period !== null && period !== ALL_PERIODS;
  const label = info ? infoLabel(info) : periodLabel(period);
  const scope = scoped ? `the ${label} close` : "every close";

  return (
    <div className="flex-none px-[34px] pt-[26px]">
      <div className="flex items-start justify-between gap-6">
        <div className="min-w-0">
          <Breadcrumb
            items={[
              { label: "CLOSE", href: routes.closeCase },
              { label: "CASE MANAGEMENT" },
            ]}
          />
          {/* The size/leading pair is restated as one arbitrary utility: the
              shared `cn` drops custom `text-*` size tokens when a text colour
              is merged alongside them (see the note in the port report). */}
          <PageTitle className="text-[46px]/[1.05]">All cases</PageTitle>
          <PageSubtitle>
            Monitor vendor-related close workflows across {scope}.
          </PageSubtitle>
        </div>
        {/* No "Create case" button: a case is what the Detection agent
            makes when it finds a PO line owed for the period. There is no
            hand-made case, so there is nothing here to offer. */}
      </div>

      {showRunStrip ? (
        <RunStrip
          period={period}
          info={info}
          canClose={canClose}
          canSettle={canSettle}
          controls={controls}
        />
      ) : null}
    </div>
  );
}
