"use client";

import type { Received, StageCheck } from "@/lib/api-types";
import { useCaseId } from "@/lib/case-context";
import { useCaseUi } from "@/lib/case-store";
import { useRevealSlice } from "@/lib/stage-reveal";
import { cn } from "@/lib/cn";
import { agentLabel } from "@/lib/trail";

import { useTrailLinks } from "./trail-links";

/** "Received from Evidence agent: 6 facts from 3 selected files", with a way to open that handoff's JSON. */
export function ReceivedStrip({ received }: { received: Received | null }) {
  const links = useTrailLinks();
  if (!received) return null;
  const counts = Object.entries(received.counts);
  return (
    <div className="rounded-lg border border-line bg-rail-alt px-3.5 py-3">
      <div className="text-nano font-semibold tracking-caps text-faint-2">RECEIVED</div>
      <div className="mt-1 text-ui leading-[1.5] text-ink-2 text-pretty">
        From {agentLabel(received.from_agent)}: {received.summary}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5">
        {counts.map(([name, value]) => (
          <span key={name} className="rounded-sm bg-wash px-1.5 py-[3px] text-nano text-muted-3 tabular-nums">
            {value} {name.replace(/_/g, " ")}
          </span>
        ))}
        <button
          type="button"
          onClick={() => links.openHandoff(received.handoff_seq)}
          className="cursor-pointer text-tiny font-medium text-accent-link hover:text-accent-press"
        >
          View the {received.payload_kind} JSON
        </button>
      </div>
    </div>
  );
}

const MARK: Record<StageCheck["status"], { ring: string; glyph: string; label: string }> = {
  PASS: { ring: "bg-accent text-white", glyph: "✓", label: "Passed" },
  FLAG: { ring: "bg-[#D6A43C] text-white", glyph: "!", label: "Flagged" },
  INFO: { ring: "bg-[#7C93B0] text-white", glyph: "i", label: "For information" },
  PENDING: { ring: "border border-rule bg-transparent text-ghost", glyph: "", label: "Pending" },
};

/**
 * The checks a stage's agents ran, one row per real check with its own status,
 * body, the log entry it came from and the evidence it rests on. The set differs
 * by purchase type, so nothing here assumes how many there are.
 */
export function StageChecks({
  checks: all,
  scope,
  offset = 0,
}: {
  checks: StageCheck[];
  scope: string;
  /** Where this list starts in the screen's reveal order. */
  offset?: number;
}) {
  const id = useCaseId();
  const links = useTrailLinks();
  const [openId, setOpenId] = useCaseUi<string | null>(id, `checks.${scope}`, null);
  const { count, working } = useRevealSlice(offset, all.length);
  const checks = all.slice(0, count);

  if (all.length === 0) {
    return <p className="text-sm text-faint-2">This stage recorded no checks.</p>;
  }

  return (
    <ol>
      {checks.map((check, index) => {
        const open = openId === check.check_id;
        const mark = MARK[check.status];
        const last = index === checks.length - 1 && !working;
        return (
          <li key={check.check_id} className={cn("relative pl-10", last ? "pb-0" : "pb-[20px]")}>
            {!last && <div className="absolute top-[22px] bottom-0 left-2 w-px bg-line" />}
            <span
              aria-label={mark.label}
              className={cn(
                "absolute top-[2px] left-0 flex h-[17px] w-[17px] items-center justify-center rounded-full text-[10px] leading-none font-bold",
                mark.ring,
              )}
            >
              {mark.glyph}
            </span>
            <button
              type="button"
              onClick={() => setOpenId(open ? null : check.check_id)}
              aria-expanded={open}
              className="flex w-full cursor-pointer items-baseline gap-3 text-left"
            >
              <span className="text-sm text-faint-3 tabular-nums">{index + 1}</span>
              <span className="min-w-0 flex-1 text-nav text-ink break-words">{check.label}</span>
              <span
                className={cn(
                  "flex-none rounded-sm px-1.5 py-[3px] text-nano leading-none font-semibold tracking-caps",
                  check.status === "PASS" && "bg-accent-soft-2 text-accent-press",
                  check.status === "FLAG" && "bg-[#F6ECD3] text-[#8A6516]",
                  check.status === "INFO" && "bg-[#E4EBF3] text-[#3F5A7C]",
                  check.status === "PENDING" && "bg-wash text-muted-3",
                )}
              >
                {check.status}
              </span>
            </button>
            {(open || check.status === "FLAG") && (
              <div className="pt-[7px] pl-[27px]">
                <p className="text-sm leading-[1.65] text-pretty text-muted-4">{check.body}</p>
                <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5">
                  {check.log_seq !== null && (
                    <button
                      type="button"
                      onClick={() => links.openLogEntry(check.log_seq as number)}
                      className="cursor-pointer text-tiny font-medium text-accent-link hover:text-accent-press"
                    >
                      log entry #{check.log_seq}
                    </button>
                  )}
                  {check.evidence_ids.map((evidenceId) => (
                    <span key={evidenceId} className="rounded-sm bg-wash px-1.5 py-[2px] font-mono text-nano text-muted-3">
                      {evidenceId}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </li>
        );
      })}
      {working && (
        <li className="relative pl-10">
          <span
            aria-hidden="true"
            className="absolute top-[2px] left-0 flex h-[17px] w-[17px] items-center justify-center rounded-full border border-rule"
          >
            <span className="h-[6px] w-[6px] animate-pulse rounded-full bg-accent" />
          </span>
          <span className="text-sm text-faint-2">Checking...</span>
        </li>
      )}
    </ol>
  );
}
