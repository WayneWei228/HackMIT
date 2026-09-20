"use client";

import Link from "next/link";
import { useState } from "react";

import { CaseMetaLine } from "@/components/ui/meta-line";
import {
  Breadcrumb,
  PageTitle,
  StatStrip,
} from "@/components/ui/primitives";
import {
  BackendUnreachable,
  LoadingRows,
  ScreenState,
} from "@/components/ui/screen-state";
import { storyPath } from "@/lib/api";
import { routes } from "@/lib/routes";
import { useLiveData } from "@/lib/use-live-data";

import { HandoffDrawer } from "../../_handoff/agent-json";
import { usd } from "../../_handoff/format";
import type { StoryStep, VendorStory } from "../../_handoff/types";
import { dayLabel } from "./story-copy";
import { storyHref } from "./story-href";
import { StoryTimeline } from "./story-timeline";
import { VendorPanel } from "./vendor-panel";

/**
 * The story of one vendor, as far as a month knows it.
 *
 * A close is not seven agents in a row: documents arrive late, an estimate is
 * forced, settlement finds a variance, a vendor is asked and answers. This
 * page tells a vendor's cases in the order those things happened - and only
 * up to the last day of the month it is cut at. December is booked on
 * January 5, so December's view does not hold it; a variance found and
 * explained in January is whole in January's view and absent before it.
 */
export function StoryScreen({
  vendor,
  caseParam,
  through,
}: {
  vendor: string | null;
  caseParam: string | null;
  through: string | null;
}) {
  const live = useLiveData<VendorStory>(storyPath(vendor, caseParam, through));
  /* Moving between vendors and months keeps the last story up until the next
     has arrived, so the page does not blank in between. */
  const [last, setLast] = useState<VendorStory | null>(null);
  if (live.data && live.data !== last) setLast(live.data);
  const story = live.status === "loading" ? last : live.data;

  const [jsonStep, setJsonStep] = useState<StoryStep | null>(null);

  if (live.status === "error") {
    return (
      <Frame>
        <BackendUnreachable
          url={live.url}
          error={live.error}
          onRetry={live.retry}
        />
      </Frame>
    );
  }

  if (!story) {
    return (
      <Frame>
        {live.status === "loading" ? (
          <LoadingRows rows={6} />
        ) : (
          <ScreenState
            title={vendor || caseParam ? "No such vendor" : "No vendor selected"}
            body={
              vendor || caseParam
                ? "The close API has no case for this vendor. Its month may not have been run."
                : "Pick a case from the case list to read how its vendor's closes went."
            }
            detail={vendor ?? caseParam}
            actions={[{ label: "All cases", href: routes.cases }]}
          />
        )}
      </Frame>
    );
  }

  const { standing } = story;
  const cutDay = dayLabel(story.through_day);

  return (
    <>
      <div className="flex-none px-[34px] pt-[26px]">
        <Breadcrumb
          items={[
            { label: "CLOSE", href: routes.cases },
            { label: "ALL CASES", href: routes.cases },
            { label: "VENDOR STORY" },
          ]}
        />
        <div className="mt-3.5 flex items-end justify-between gap-8">
          <div className="min-w-0">
            <PageTitle className="mt-0 text-[46px] leading-[1.02]">
              {story.vendor_name}
            </PageTitle>
            <div className="font-display mt-0.5 text-4xl leading-[1.1] tracking-tight text-ink-deep">
              as it stood on {cutDay}
            </div>
            <CaseMetaLine
              className="mt-[15px]"
              items={[
                story.label ?? "Not classified",
                story.steps.length === 1
                  ? "1 event so far"
                  : `${story.steps.length} events so far`,
              ]}
            />
          </div>
          <StatStrip
            className="pb-1"
            stats={[
              {
                label: "Accrued, actual not in yet",
                value: usd(standing.accrued_open),
              },
              { label: "True-ups booked", value: usd(standing.true_ups, true) },
              {
                label:
                  standing.open_questions === 1
                    ? "Question still out"
                    : "Questions still out",
                value: String(standing.open_questions),
              },
            ]}
          />
        </div>

        <Months story={story} />
      </div>

      <div className="h-px flex-none bg-line" />

      <div className="flex min-h-0 flex-1">
        <VendorPanel story={story} />
        <div className="min-h-0 flex-1 overflow-y-auto px-[34px] pt-7 pb-16">
          <StoryTimeline
            /* Another vendor or month is another story: its opening plays again. */
            key={`${story.vendor_id}:${story.through}`}
            story={story}
            onJson={setJsonStep}
          />
        </div>
      </div>

      {jsonStep && (
        <HandoffDrawer
          key={`${jsonStep.case_id}:${jsonStep.case_step}`}
          agentId={jsonStep.agent}
          caseParam={jsonStep.case_id}
          startStep={jsonStep.case_step}
          onClose={() => setJsonStep(null)}
        />
      )}
    </>
  );
}

function Frame({ children }: { children: React.ReactNode }) {
  return <div className="flex-1 px-[34px] pt-[26px]">{children}</div>;
}

/** The calendar months anything happened in. A month shows what was known by its last day. */
function Months({ story }: { story: VendorStory }) {
  if (story.months.length === 0) return <div className="h-6" />;
  return (
    <nav aria-label="Cut the story at the end of" className="mt-6 flex gap-6">
      {story.months.map((item) => {
        const active = item.month === story.through;
        return (
          <Link
            key={item.month}
            href={storyHref(story.vendor_id, item.month)}
            aria-current={active ? "page" : undefined}
            className={`-mb-px border-b-2 pb-3 text-body transition-colors duration-[160ms] ${
              active
                ? "border-accent font-medium text-ink"
                : "border-transparent text-faint-2 hover:text-ink"
            }`}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
