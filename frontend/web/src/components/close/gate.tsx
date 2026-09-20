import type { SVGProps } from "react";

import type { GateResult, GateVerdict } from "@/lib/api-types";
import { cn } from "@/lib/cn";
import { VERDICT_STYLES } from "@/lib/trail";

/** A shield with a check: the mark for anything the formal verifier decided. */
export function ShieldCheckIcon({ size = 13, ...props }: SVGProps<SVGSVGElement> & { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 14 14" fill="none" aria-hidden="true" {...props}>
      <path
        d="M7 1.4 2.4 3v3.6c0 2.7 1.9 4.6 4.6 6 2.7-1.4 4.6-3.3 4.6-6V3L7 1.4Z"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinejoin="round"
      />
      <path
        d="m4.9 7.1 1.5 1.5 2.8-3"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function VerdictChip({ verdict, className }: { verdict: GateVerdict; className?: string }) {
  const style = VERDICT_STYLES[verdict];
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-sm px-1.5 py-[3px] text-nano leading-none font-semibold tracking-caps",
        style.chip,
        className,
      )}
    >
      {style.label}
    </span>
  );
}

/** "Formal verification" badge with the shield, used on every verifier entry. */
export function FormalVerificationBadge({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-sm bg-accent-tint px-1.5 py-[3px] text-nano leading-none font-semibold tracking-caps text-accent-deep ring-1 ring-accent-line-2 ring-inset",
        className,
      )}
    >
      <ShieldCheckIcon size={11} />
      FORMAL VERIFICATION
    </span>
  );
}

/** "8/8 checks passed", coloured by whether every control held. */
export function GateTally({ gate }: { gate: GateResult }) {
  const clean = gate.passed === gate.total;
  return (
    <span
      className={cn(
        "text-meta font-medium tabular-nums",
        clean ? "text-accent-press" : "text-[#A4452F]",
      )}
    >
      {gate.passed}/{gate.total} checks passed
    </span>
  );
}

/** Every control the verifier ran at a handoff, with what it expected and what it found. */
export function GateChecklist({ gate }: { gate: GateResult }) {
  return (
    <div className="mt-2.5 rounded-lg border border-line bg-panel">
      <div className="flex items-center justify-between gap-3 border-b border-line px-3 py-2 text-tiny text-faint-2">
        <span>Controls checked before the next agent starts</span>
        <span className="font-mono tabular-nums">policy v{gate.policy_version}</span>
      </div>
      <ul className="divide-y divide-divider-3">
        {gate.checks.map((check) => (
          <li key={check.check_id} className="flex gap-2.5 px-3 py-2">
            <span
              aria-label={check.passed ? "Passed" : "Failed"}
              className={cn(
                "mt-[2px] flex h-[14px] w-[14px] flex-none items-center justify-center rounded-full text-[9px] leading-none font-bold text-white",
                check.passed ? "bg-accent" : "bg-[#C2543D]",
              )}
            >
              {check.passed ? "✓" : "×"}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                <span className="font-mono text-tiny font-medium text-ink-2">{check.check_id}</span>
                <span className="text-meta text-ink-3 text-pretty">{check.sentence}</span>
              </div>
              {(check.expected !== null || check.actual !== null) && (
                <div className="mt-1 grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5 font-mono text-tiny text-muted-4">
                  {check.expected !== null && (
                    <>
                      <span className="text-ghost">expected</span>
                      <span className="break-words text-ink-3">{check.expected}</span>
                    </>
                  )}
                  {check.actual !== null && (
                    <>
                      <span className="text-ghost">actual</span>
                      <span
                        className={cn(
                          "break-words",
                          check.passed ? "text-ink-3" : "font-medium text-[#A4452F]",
                        )}
                      >
                        {check.actual}
                      </span>
                    </>
                  )}
                </div>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
