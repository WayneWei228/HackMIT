import Link from "next/link";

import { JsonViewer } from "@/components/close/json-viewer";
import { EmptyReport, MonthLinks, ReportFrame, tokenLabel } from "@/components/reports/report-frame";
import { getVendorStory, getVendors, getObligation } from "@/lib/api";
import { caseHref } from "@/lib/case-nav";
import type { SearchParams } from "@/lib/load-case";
import type { StoryEvent, StoryLetter } from "@/lib/report-types";
import { routes } from "@/lib/routes";
import { formatStamp } from "@/lib/time";
import { agentLabel } from "@/lib/trail";

import { Letter } from "./_components/letter";

export const metadata = { title: "Vendor story - TrueUp" };

const LETTER_METHOD: Record<StoryLetter["method"], string> = {
  LLM: "worded by the model",
  TEMPLATE: "worded from a template",
  SCRIPTED_REPLY: "scripted reply",
};

/** The question the close sent, or the answer it got, shown whole. */
function StoryLetterSheet({ event }: { event: StoryEvent }) {
  const letter = event.payload as StoryLetter;
  const sent = letter.direction === "OUT";
  const party = sent ? letter.to : letter.from;
  return (
    <Letter
      direction={sent ? "sent" : "received"}
      party={party.role ? `${party.name}, ${party.role}` : party.name}
      date={formatStamp(event.at).date}
      subject={event.title}
      body={event.summary}
      footnote={`Simulated email · ${tokenLabel(letter.topic)} · ${LETTER_METHOD[letter.method]}`}
    />
  );
}

export default async function StoryPage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const vendors = (await getVendors()).vendors;
  const obligation = typeof params.o === "string" ? await getObligation(params.o) : null;
  const vendor = typeof params.vendor === "string" ? params.vendor : obligation?.header.vendor_id ?? vendors[0]?.vendor_id;
  if (!vendor) return <ReportFrame title="Vendor story" description="The recorded history of each vendor."><EmptyReport>No vendors are available yet.</EmptyReport></ReportFrame>;
  const through = typeof params.through === "string" ? params.through : undefined;
  const story = await getVendorStory(vendor, through);
  const storyHref = `${routes.story}?vendor=${encodeURIComponent(vendor)}`;
  return <ReportFrame title={`${story.vendor_name} story`}
    description={`Recorded events through ${formatStamp(story.through_at).date}. All data and correspondence are simulated.`}
    toolbar={<>
      <nav aria-label="Vendor" className="mt-5 flex flex-wrap gap-4">
        {vendors.map((item) => <Link key={item.vendor_id} aria-current={item.vendor_id === vendor ? "page" : undefined}
          href={`${routes.story}?vendor=${encodeURIComponent(item.vendor_id)}${through ? `&through=${encodeURIComponent(through)}` : ""}`}
          className={item.vendor_id === vendor ? "text-sm font-semibold text-accent-deep" : "text-sm text-muted hover:underline"}>{item.name}</Link>)}
      </nav>
      <MonthLinks months={Array.from(new Set([...story.months, story.through])).sort()} selected={story.through} href={storyHref} all={false} param="through" />
    </>}>
    <p className="mb-6 text-sm text-muted">{story.events.length} recorded events</p>
    {story.events.length === 0 ? <EmptyReport>No events had been recorded by this month.</EmptyReport> : (
      <ol className="ml-3 space-y-7 border-l border-line pl-7">
        {story.events.map((event) => <li key={event.id} className="relative">
          <span aria-hidden="true" className="absolute -left-[34px] top-1.5 h-3 w-3 rounded-full border-2 border-paper bg-accent" />
          <div className="mb-2 flex items-center gap-3 text-xs text-faint">
            <time dateTime={event.at}>{formatStamp(event.at).date} · {formatStamp(event.at).time} UTC</time>
            <span>{event.agent ? agentLabel(event.agent) : "Case"}</span>
            <span>Close {event.period}</span>
          </div>
          {event.kind === "LETTER" ? <StoryLetterSheet event={event} /> : <article className="rounded-xl border border-line bg-panel p-5">
            <h2 className="font-medium">{event.title}</h2>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-muted">{event.summary}</p>
            <div className="mt-4 flex gap-4">
              <Link className="text-sm text-accent-deep hover:underline" href={caseHref(routes.closeCase, event.obligation_id)}>Open case →</Link>
            </div>
            <details className="mt-4"><summary className="cursor-pointer text-xs text-muted">View recorded JSON</summary><JsonViewer className="mt-2" value={event.payload} /></details>
          </article>}
        </li>)}
      </ol>
    )}
  </ReportFrame>;
}
