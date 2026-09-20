import { Breadcrumb, PageSubtitle, PageTitle } from "@/components/ui/primitives";
import { CloseControls } from "@/components/close/close-controls";
import type { CloseView } from "@/lib/api-types";
import { routes } from "@/lib/routes";

/** Page title block: where you are, what this list is, and how to move the close along. */
export function CasesHeader({ close }: { close: CloseView }) {
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
            Monitor vendor-related close workflows across the December close.
          </PageSubtitle>
        </div>
        <CloseControls close={close} />
      </div>
    </div>
  );
}
