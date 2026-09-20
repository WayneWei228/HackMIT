"use client";

import { useEffect, useMemo, useRef } from "react";
import type { ReactNode } from "react";

import { ChevronDownIcon } from "@/components/ui/icons";
import type { LogEntry } from "@/lib/api-types";
import { useCaseId } from "@/lib/case-context";
import { useCaseTrail } from "@/lib/case-trail";
import { useCaseUi, type StageKey } from "@/lib/case-store";
import { cn } from "@/lib/cn";
import { useStageNarration } from "@/lib/stage-narration";
import { formatStamp } from "@/lib/time";
import { VERDICT_STYLES, agentLabel, outgoingHandoff, verificationTotals } from "@/lib/trail";

import { GateChecklist, GateTally, FormalVerificationBadge, VerdictChip } from "./gate";
import { HandoffCard, HandoffFlow, useOpenHandoffs } from "./handoff-card";
import { EntryDetail, MethodTag, RunTag } from "./trail-parts";

type Tab = "log" | "handoffs";
type Filter = "all" | "verification";

function usePanelState() {
  const id = useCaseId();
  const [open, setOpen] = useCaseUi(id, "trail.open", false);
  const [tab, setTab] = useCaseUi<Tab>(id, "trail.tab", "log");
  const [filter, setFilter] = useCaseUi<Filter>(id, "trail.filter", "all");
  return { open, setOpen, tab, setTab, filter, setFilter };
}

/** The status bar's narration: the newest recorded step of this stage, or an honest state. */
export function NarrationText({ screen }: { screen: StageKey }) {
  const { text, phase } = useStageNarration(screen);
  return (
    <span
      className={cn(
        "truncate text-ui whitespace-nowrap",
        phase === "error" ? "text-[#A4452F]" : "text-faint-3",
      )}
    >
      {text}
    </span>
  );
}

/**
 * Wraps the left side of an agent status bar so clicking it opens the reasoning
 * log beneath it. It also carries the running tally of formal-verification
 * controls, so a viewer sees them before opening anything.
 */
export function TrailToggle({ children }: { children: ReactNode }) {
  const { open, setOpen } = usePanelState();
  const { log } = useCaseTrail();
  const totals = useMemo(() => verificationTotals(log?.entries ?? []), [log]);

  return (
    <button
      type="button"
      onClick={() => setOpen(!open)}
      aria-expanded={open}
      aria-label={open ? "Collapse the agent reasoning log" : "Expand the agent reasoning log"}
      className="group flex min-w-0 cursor-pointer items-center gap-[11px] rounded-lg py-1 pr-2 text-left transition-colors duration-[160ms] hover:bg-wash"
    >
      {children}
      {totals.total > 0 && (
        <span className="flex-none rounded-sm bg-accent-tint px-1.5 py-[3px] text-nano leading-none font-semibold whitespace-nowrap text-accent-deep ring-1 ring-accent-line-2 ring-inset">
          {totals.passed}/{totals.total} verification checks passed
        </span>
      )}
      <ChevronDownIcon
        size={13}
        className={cn(
          "flex-none text-faint-2 transition-transform duration-[160ms] group-hover:text-ink",
          open && "rotate-180",
        )}
      />
    </button>
  );
}

function StateNote({ children }: { children: ReactNode }) {
  return <div className="px-4 py-6 text-meta leading-[1.6] text-faint-2 text-pretty">{children}</div>;
}

const KIND_BADGES: Partial<Record<LogEntry["kind"], { label: string; chip: string }>> = {
  HUMAN_OVERRIDE: { label: "HUMAN OVERRIDE", chip: "bg-[#F6ECD3] text-[#8A6516]" },
  CONTROLLER: { label: "CONTROLLER", chip: "bg-[#E4EBF3] text-[#3F5A7C]" },
  REVIEW: { label: "REVIEWER", chip: "bg-[#EDE8F5] text-[#5B4A86]" },
};

function railFor(entry: LogEntry): string {
  if (entry.kind === "VERIFICATION" && entry.verification) return VERDICT_STYLES[entry.verification.verdict].rail;
  if (entry.kind === "VERIFICATION") return "bg-accent";
  if (entry.kind === "HUMAN_OVERRIDE") return "bg-[#D6A43C]";
  if (entry.kind === "CONTROLLER") return "bg-[#7C93B0]";
  if (entry.kind === "REVIEW") return "bg-[#8A78B8]";
  return "bg-transparent";
}

function EntryRow({ entry, open, onToggle }: { entry: LogEntry; open: boolean; onToggle: () => void }) {
  const gate = entry.verification;
  const verification = entry.kind === "VERIFICATION";
  const badge = KIND_BADGES[entry.kind];
  return (
    <li
      className={cn(
        "relative border-b border-divider-3 py-2.5 pr-4 pl-5",
        verification && "bg-accent-tint/60",
        entry.kind === "HUMAN_OVERRIDE" && "bg-[#FBF5E6]",
        entry.superseded && "opacity-55",
      )}
    >
      <span aria-hidden="true" className={cn("absolute top-0 bottom-0 left-0 w-[3px]", railFor(entry))} />
      <div className="flex gap-3">
        <div className="w-[64px] flex-none pt-[1px] text-tiny text-faint-2 tabular-nums">
          {formatStamp(entry.at).time}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="text-meta font-medium text-ink">{agentLabel(entry.agent)}</span>
            {verification && <FormalVerificationBadge />}
            {badge && (
              <span
                className={cn(
                  "inline-flex items-center rounded-sm px-1.5 py-[3px] text-nano leading-none font-semibold tracking-caps",
                  badge.chip,
                )}
              >
                {badge.label}
              </span>
            )}
            <MethodTag method={entry.method} />
            {gate && <VerdictChip verdict={gate.verdict} />}
            {gate && <GateTally gate={gate} />}
            {entry.superseded && (
              <span className="text-nano font-medium text-faint-2">superseded by a later re-run</span>
            )}
          </div>
          <div className={cn("mt-1 text-ui text-ink text-pretty", entry.superseded && "line-through")}>
            {entry.title}
          </div>
          {entry.summary && entry.summary !== entry.title && (
            <div className="mt-0.5 text-meta leading-[1.55] text-muted-3 text-pretty">{entry.summary}</div>
          )}
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
            <RunTag runId={entry.run_id} />
            <button
              type="button"
              onClick={onToggle}
              aria-expanded={open}
              className="cursor-pointer text-tiny font-medium text-accent-link hover:text-accent-press"
            >
              {open ? "Hide detail" : gate ? "Show the controls checked" : "Show detail"}
            </button>
          </div>
          {open && (gate ? <GateChecklist gate={gate} /> : null)}
          {open && <EntryDetail entry={entry} />}
        </div>
      </div>
    </li>
  );
}

function LogList({ entries, filter }: { entries: LogEntry[]; filter: Filter }) {
  const id = useCaseId();
  const [openSeqs, setOpenSeqs] = useCaseUi<number[]>(id, "trail.entries", []);
  const shown = filter === "verification" ? entries.filter((entry) => entry.kind === "VERIFICATION") : entries;
  const overrideSeq = entries.reduce<number | null>(
    (latest, entry) => (entry.kind === "HUMAN_OVERRIDE" && (latest === null || entry.seq > latest) ? entry.seq : latest),
    null,
  );

  if (shown.length === 0) {
    return (
      <StateNote>
        {filter === "verification"
          ? "No formal-verification gate has run for this case yet. Each handoff between agents is checked here."
          : "Nothing has been recorded for this case yet. Start it and each agent's steps appear here as its call returns."}
      </StateNote>
    );
  }

  return (
    <ul>
      {shown.map((entry, index) => {
        const previous = shown[index - 1];
        const afterOverride =
          overrideSeq !== null && entry.seq > overrideSeq && (!previous || previous.seq <= overrideSeq);
        return (
          <div key={entry.seq}>
            {afterOverride && (
              <li className="border-b border-[#EBD9A8] bg-[#FBF5E6] px-5 py-2 text-tiny font-medium text-[#8A6516]">
                Re-run after the file removal: the entries below replace the earlier ones for the same agents.
              </li>
            )}
            <EntryRow
              entry={entry}
              open={openSeqs.includes(entry.seq)}
              onToggle={() =>
                setOpenSeqs(
                  openSeqs.includes(entry.seq)
                    ? openSeqs.filter((seq) => seq !== entry.seq)
                    : [...openSeqs, entry.seq],
                )
              }
            />
          </div>
        );
      })}
    </ul>
  );
}

/**
 * The expandable trail under an agent status bar: the recorded log of every
 * agent step (with the formal-verification gates picked out) and the handoffs
 * between agents. It reads only the backend's run log, so when that cannot be
 * read it says so.
 */
export function TrailPanel() {
  const { open, setOpen, tab, setTab, filter, setFilter } = usePanelState();
  const trail = useCaseTrail();
  const entries = useMemo(
    () => [...(trail.log?.entries ?? [])].sort((a, b) => a.seq - b.seq),
    [trail.log],
  );
  const handoffs = trail.handoffs?.handoffs ?? [];
  const gates = entries.filter((entry) => entry.kind === "VERIFICATION").length;

  const scroller = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  useEffect(() => {
    const node = scroller.current;
    if (!open || !node) return;
    if (tab === "handoffs") {
      /* Handoffs read from the first agent down, so start at the top. */
      node.scrollTop = 0;
      stick.current = false;
    } else if (stick.current) {
      node.scrollTop = node.scrollHeight;
    }
  }, [open, tab, filter, entries.length]);

  if (!open) return null;

  let body: ReactNode;
  if (trail.status === "loading") body = <StateNote>Reading the run log from the backend...</StateNote>;
  else if (trail.status === "error")
    body = <StateNote>Could not read the run log from the backend: {trail.error}</StateNote>;
  else if (trail.unavailable)
    body = (
      <StateNote>
        This backend build has no run log endpoint, so there is no reasoning trail to show. Nothing here is
        filled in from a script.
      </StateNote>
    );
  else if (tab === "handoffs") body = <HandoffFlow handoffs={handoffs} />;
  else body = <LogList entries={entries} filter={filter} />;

  return (
    <section
      aria-label="Agent reasoning log"
      className="flex max-h-[min(42vh,400px)] min-h-0 flex-none flex-col border-y border-line bg-paper-sunk"
    >
      <div className="flex flex-none flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-line bg-paper-sunk px-[34px] py-2.5">
        <div className="min-w-0">
          <div className="text-ui font-medium text-ink">Agent reasoning log</div>
          <div className="text-tiny text-faint-2 text-pretty">
            The recorded trail of what each agent read, decided and flagged, read live from the backend run log. It
            is not model chain-of-thought.
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div role="tablist" className="flex rounded-lg border border-line bg-panel p-0.5">
            {(
              [
                ["log", `Reasoning log (${entries.length})`],
                ["handoffs", `Handoffs (${handoffs.length})`],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={tab === key}
                onClick={() => setTab(key)}
                className={cn(
                  "cursor-pointer rounded-md px-2.5 py-1 text-tiny font-medium transition-colors duration-[160ms]",
                  tab === key ? "bg-accent-soft text-accent-press" : "text-muted-4 hover:text-ink",
                )}
              >
                {label}
              </button>
            ))}
          </div>
          {tab === "log" && (
            <div role="group" aria-label="Filter the log" className="flex rounded-lg border border-line bg-panel p-0.5">
              {(
                [
                  ["all", "All"],
                  ["verification", `Formal verification only (${gates})`],
                ] as const
              ).map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  aria-pressed={filter === key}
                  onClick={() => setFilter(key)}
                  className={cn(
                    "cursor-pointer rounded-md px-2.5 py-1 text-tiny font-medium transition-colors duration-[160ms]",
                    filter === key ? "bg-accent-soft text-accent-press" : "text-muted-4 hover:text-ink",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          )}
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="cursor-pointer rounded-md px-2 py-1 text-tiny font-medium text-muted-4 hover:text-ink"
          >
            Close
          </button>
        </div>
      </div>
      <div
        ref={scroller}
        onScroll={(event) => {
          const node = event.currentTarget;
          stick.current = node.scrollHeight - node.scrollTop - node.clientHeight < 48;
        }}
        className="min-h-0 flex-1 overflow-y-auto overscroll-contain"
      >
        {body}
      </div>
    </section>
  );
}

/**
 * The handoff a stage passes on, shown in its rail: the JSON the producer
 * emitted and the verifier's verdict on it. Renders nothing until that handoff
 * has really happened.
 */
export function InlineHandoff({ screen }: { screen: StageKey }) {
  const { handoffs } = useCaseTrail();
  const [open, toggle] = useOpenHandoffs();
  const handoff = outgoingHandoff(screen, handoffs?.handoffs ?? []);
  if (!handoff) return null;
  return (
    <div className="mt-[22px]">
      <div className="mb-2 text-eyebrow font-medium tracking-caps-lg text-faint">HANDOFF PAYLOAD</div>
      <HandoffCard handoff={handoff} open={open.includes(handoff.seq)} onToggle={() => toggle(handoff.seq)} compact />
    </div>
  );
}
