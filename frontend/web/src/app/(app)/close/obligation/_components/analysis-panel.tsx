"use client";

import { PendingRows } from "@/components/close/pending-rows";
import { ReceivedStrip, StageChecks } from "@/components/close/stage-checks";
import { useStagePending } from "@/lib/stage-reveal";

import { Panel, PanelHeading } from "./panel";
import { useObligationScreen } from "./screen-context";

/**
 * Middle column: what this stage received and the checks its agents ran. Both
 * come from the backend; when it has sent none the panel says so rather than
 * listing checks of its own.
 */
export function AnalysisPanel() {
  const { received, checks } = useObligationScreen();
  const pending = useStagePending();

  return (
    <Panel className="px-[22px] pt-5 pb-[22px]">
      <PanelHeading>Obligation analysis</PanelHeading>
      <div className="mt-3">
        <ReceivedStrip received={received} />
      </div>

      <div className="mt-5">
        {pending ? (
          <PendingRows />
        ) : checks ? (
          <StageChecks checks={checks} scope="obligation" />
        ) : (
          <p className="text-sm leading-[1.6] text-faint-2 text-pretty">
            The backend did not return this stage&apos;s checks, so none are shown.
          </p>
        )}
      </div>
    </Panel>
  );
}
