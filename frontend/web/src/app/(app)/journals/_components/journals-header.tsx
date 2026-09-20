import {
  Breadcrumb,
  PageSubtitle,
  PageTitle,
} from "@/components/ui/primitives";
import { routes } from "@/lib/routes";
import { ALL_PERIODS, infoLabel, periodLabel, type PeriodInfo } from "@/lib/period";

/**
 * Page title block.
 *
 * The subtitle names the selected month rather than a fixed one - no screen
 * in this product knows what month it is.
 */
export function JournalsHeader({
  period,
  info,
}: {
  /** The selected month, `ALL_PERIODS`, or `null` before one is resolved. */
  period: string | null;
  info: PeriodInfo | null;
}) {
  const scoped = period !== null && period !== ALL_PERIODS;
  const label = info ? infoLabel(info) : periodLabel(period);
  const scope = scoped ? `the ${label} close` : "every close";

  return (
    <div className="flex-none px-[34px] pt-[26px]">
      <Breadcrumb
        items={[
          { label: "CLOSE", href: routes.closeCase },
          { label: "JOURNALS" },
        ]}
      />
      {/* The size/leading pair is restated as one arbitrary utility - see the
          note on the cases header about `cn` and custom size tokens. */}
      <PageTitle className="text-[46px]/[1.05]">Journals</PageTitle>
      <PageSubtitle>
        Every entry posted by {scope}, with the accounts it books.
      </PageSubtitle>
    </div>
  );
}
