import {
  Breadcrumb,
  PageSubtitle,
  PageTitle,
} from "@/components/ui/primitives";
import { ALL_PERIODS, infoLabel, periodLabel, type PeriodInfo } from "@/lib/period";

/**
 * Page title block.
 *
 * Documents are not part of the close section - they are the raw intake the
 * whole product is built from - so the breadcrumb has a single crumb.
 */
export function DocumentsHeader({
  period,
  info,
}: {
  /** The selected month, `ALL_PERIODS`, or `null` before one is resolved. */
  period: string | null;
  info: PeriodInfo | null;
}) {
  const scoped = period !== null && period !== ALL_PERIODS;
  const label = info ? infoLabel(info) : periodLabel(period);
  const scope = scoped ? `in ${label}` : "in every month";

  return (
    <div className="flex-none px-[34px] pt-[26px]">
      <Breadcrumb items={[{ label: "DOCUMENTS" }]} />
      {/* The size/leading pair is restated as one arbitrary utility - see the
          note on the cases header about `cn` and custom size tokens. */}
      <PageTitle className="text-[46px]/[1.05]">Documents</PageTitle>
      <PageSubtitle>
        Every file the close could read {scope}, and what came out of it.
      </PageSubtitle>
    </div>
  );
}
