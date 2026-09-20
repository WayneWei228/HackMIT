"use client";

import type { Handoff } from "@/lib/api-types";
import { useCaseId } from "@/lib/case-context";
import { useCaseUi } from "@/lib/case-store";
import { cn } from "@/lib/cn";
import { agentLabel, stageLabel } from "@/lib/trail";

import { GateChecklist, GateTally, ShieldCheckIcon, VerdictChip } from "./gate";
import { JsonViewer } from "./json-viewer";
import { RunTag } from "./trail-parts";

/** Which handoff cards the reader has opened, remembered across screens. */
export function useOpenHandoffs(): [readonly number[], (seq: number) => void] {
  const id = useCaseId();
  const [open, setOpen] = useCaseUi<number[]>(id, "handoff.open", []);
  const toggle = (seq: number) =>
    setOpen(open.includes(seq) ? open.filter((value) => value !== seq) : [...open, seq]);
  return [open, toggle];
}

/**
 * One handoff between two agents: the typed JSON the producer emitted, the
 * verifier's verdict on it, and the ids of the database rows it was built from.
 * The story reads top to bottom - producer emits JSON, the gate checks it, the
 * consumer receives it.
 */
export function HandoffCard({
  handoff,
  open,
  onToggle,
  compact = false,
}: {
  handoff: Handoff;
  open: boolean;
  onToggle: () => void;
  compact?: boolean;
}) {
  const gate = handoff.verification;
  return (
    <div
      className={cn(
        "rounded-lg border bg-panel transition-colors duration-[160ms]",
        open ? "border-accent-line" : "border-line",
      )}
    >
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full cursor-pointer flex-col gap-1.5 px-3 py-2.5 text-left"
      >
        <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
          <span className="text-meta font-medium text-ink">{agentLabel(handoff.from_agent)}</span>
          <span aria-hidden="true" className="text-ghost-2">
            {"→"}
          </span>
          <span className="text-meta font-medium text-ink">{agentLabel(handoff.to_agent)}</span>
          <span className="ml-auto font-mono text-nano text-muted-4">
            {open ? "hide JSON" : "show JSON"}
          </span>
        </div>
        <div className="flex min-w-0 flex-wrap items-center gap-x-2.5 gap-y-1 text-tiny text-muted-4">
          <span className="font-mono">
            {handoff.stage_from === handoff.stage_to
              ? `Stays in ${stageLabel(handoff.stage_from)}`
              : `${stageLabel(handoff.stage_from)} → ${stageLabel(handoff.stage_to)}`}
          </span>
          <span className="rounded-sm bg-wash px-1.5 py-[2px] font-mono text-nano text-muted-3">
            {handoff.payload_kind}
          </span>
          {gate && (
            <span className="flex items-center gap-1.5">
              <ShieldCheckIcon size={12} className="text-accent" />
              <VerdictChip verdict={gate.verdict} />
              <GateTally gate={gate} />
            </span>
          )}
        </div>
      </button>

      {open && (
        <div className={cn("border-t border-line px-3 pb-3", compact ? "pt-2" : "pt-2.5")}>
          <div className="mb-1 flex items-center justify-between gap-2 text-nano font-semibold tracking-caps text-faint-2">
            <span>PAYLOAD THE PRODUCER EMITTED</span>
            <RunTag runId={handoff.run_id} prefix="run log" />
          </div>
          <JsonViewer value={handoff.payload} maxHeight={compact ? 220 : 300} />
          {(handoff.record_ids ?? []).length > 0 && (
            <div className="mt-2 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 font-mono text-nano text-muted-4">
              <span className="text-ghost">built from</span>
              <span className="break-words">{(handoff.record_ids ?? []).join(", ")}</span>
            </div>
          )}
          {gate ? (
            <>
              <div className="mt-3 mb-1 text-nano font-semibold tracking-caps text-faint-2">
                VERIFIER GATE BEFORE THE NEXT AGENT STARTED
              </div>
              <GateChecklist gate={gate} />
            </>
          ) : (
            <div className="mt-2 text-meta text-faint-2">No verifier result was recorded for this handoff.</div>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Every handoff of the case as a vertical flow: agent nodes joined by arrows,
 * each arrow a card that opens onto the JSON that crossed it.
 */
export function HandoffFlow({ handoffs }: { handoffs: readonly Handoff[] }) {
  const [open, toggle] = useOpenHandoffs();
  const ordered = [...handoffs].sort((a, b) => a.seq - b.seq);

  if (ordered.length === 0) {
    return <div className="px-4 py-6 text-meta text-faint-2">No handoff has happened yet.</div>;
  }

  return (
    <ol className="flex flex-col items-stretch px-4 py-3">
      {ordered.map((handoff, index) => {
        const previous = ordered[index - 1];
        const showFrom = !previous || previous.to_agent !== handoff.from_agent;
        return (
          <li key={handoff.seq} className="flex flex-col items-center">
            {showFrom && <AgentNode name={handoff.from_agent} />}
            <Connector />
            <div className="w-full max-w-[640px]">
              <HandoffCard handoff={handoff} open={open.includes(handoff.seq)} onToggle={() => toggle(handoff.seq)} />
            </div>
            <Connector arrow />
            <AgentNode name={handoff.to_agent} />
          </li>
        );
      })}
    </ol>
  );
}

function AgentNode({ name }: { name: string }) {
  return (
    <div className="rounded-full border border-line-dark bg-panel px-3.5 py-1.5 text-meta font-medium text-ink shadow-tile">
      {agentLabel(name)}
    </div>
  );
}

function Connector({ arrow = false }: { arrow?: boolean }) {
  return (
    <div className="flex flex-col items-center" aria-hidden="true">
      <div className="h-3.5 w-px bg-rule" />
      {arrow && <div className="-mt-px text-[9px] leading-none text-ghost">{"▼"}</div>}
    </div>
  );
}
