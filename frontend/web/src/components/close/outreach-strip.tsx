"use client";

import { MailIcon } from "@/components/ui/icons";
import { useCaseId } from "@/lib/case-context";
import { cn } from "@/lib/cn";
import { outreachPanel } from "@/lib/outreach-panel";

import { counterpartOf, sentLabel, statusOf, topicLabel, useOutreachThreads } from "./outreach-thread";

/** One line per email on the case, under the ribbon, on every stage screen. Click opens the email. */
export function OutreachStrip() {
  const id = useCaseId();
  const threads = useOutreachThreads(id);
  if (!id || threads.length === 0) return null;
  return (
    <ul aria-label="Emails on this case" className="mt-2.5 flex flex-col gap-1.5">
      {threads.map((thread) => {
        const state = statusOf(thread);
        const sent = sentLabel(thread);
        const waiting = thread.status === "SENT";
        return (
          <li key={thread.thread_id}>
            <button
              type="button"
              onClick={() => outreachPanel.open(id, thread.thread_id)}
              className="group flex w-full cursor-pointer items-center gap-3 rounded-lg border border-divider bg-panel px-3.5 py-2.5 text-left transition-colors duration-[160ms] hover:bg-panel-hover focus-visible:shadow-[var(--shadow-ring)] focus-visible:outline-none"
            >
              <span className="flex h-[26px] w-[26px] flex-none items-center justify-center rounded-md bg-wash text-muted-3">
                <MailIcon size={15} />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-ui leading-[1.3] text-ink">
                  Email to {counterpartOf(thread)}
                  <span className="text-faint-2"> - {topicLabel(thread.topic)}</span>
                </span>
                <span className="mt-[3px] flex items-center gap-1.5 text-meta leading-[1.3] text-muted-3">
                  <span className="relative flex h-[7px] w-[7px] flex-none">
                    {waiting && (
                      <span
                        className="animate-pulse-ring absolute inset-0 rounded-full opacity-50"
                        style={{ background: state.mark }}
                      />
                    )}
                    <span
                      className="relative h-[7px] w-[7px] rounded-full"
                      style={{ background: state.mark }}
                    />
                  </span>
                  <span className={cn("truncate", waiting && "font-medium text-ink")}>
                    {state.text}
                    {waiting && sent ? ` - email sent ${sent}` : ""}
                  </span>
                </span>
              </span>
              <span className="flex-none rounded-sm bg-[#F6ECD3] px-1.5 py-[3px] text-nano leading-none font-medium text-[#8A6516]">
                Synthetic
              </span>
              <span className="flex-none text-meta font-medium text-accent-link group-hover:underline">
                View email
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

/** A small link that opens the case's email panel; it renders nothing when the case sent no email. */
export function ViewEmailLink({ label = "View the email", className }: { label?: string; className?: string }) {
  const id = useCaseId();
  const threads = useOutreachThreads(id);
  if (!id || threads.length === 0) return null;
  const waiting = threads.find((thread) => thread.status === "SENT") ?? threads[0];
  return (
    <button
      type="button"
      onClick={() => outreachPanel.open(id, waiting.thread_id)}
      className={cn(
        "inline-flex cursor-pointer items-center gap-1.5 text-meta font-medium text-accent-link hover:underline focus-visible:shadow-[var(--shadow-ring)] focus-visible:outline-none",
        className,
      )}
    >
      <MailIcon size={13} />
      {label}
    </button>
  );
}

/** Under the case status: who the case is waiting on and when the email went out. Nothing when it is not waiting. */
export function WaitingLine({ className }: { className?: string }) {
  const id = useCaseId();
  const threads = useOutreachThreads(id);
  const thread = threads.find((t) => t.status === "SENT");
  if (!id || !thread) return null;
  const sent = sentLabel(thread);
  return (
    <button
      type="button"
      onClick={() => outreachPanel.open(id, thread.thread_id)}
      className={cn(
        "cursor-pointer text-left text-meta leading-[1.4] text-muted-3 text-pretty hover:text-ink hover:underline focus-visible:shadow-[var(--shadow-ring)] focus-visible:outline-none",
        className,
      )}
    >
      {statusOf(thread).text}
      {sent ? ` - email sent ${sent}` : ""}
    </button>
  );
}
