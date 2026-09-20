import { STATUS_STYLES, type CaseStatus } from "../_data";

/**
 * The status marker: a solid dot, ringed by a slow pulse while the agent is
 * still running. The shared `StatusDot` primitive only knows four fixed tones
 * and fills its ring, while the comp draws a hairline ring around five
 * per-status colours - so this screen carries its own.
 */
export function CaseStatusDot({ status }: { status: CaseStatus }) {
  const { dot, pulse } = STATUS_STYLES[status];

  return (
    <span className="relative h-2 w-2 flex-none">
      <span
        className="absolute inset-0 rounded-full"
        style={{ background: dot }}
      />
      {pulse && (
        <span className="animate-pulse-ring absolute -inset-1 rounded-full border-[1.2px] border-[rgba(46,128,71,0.5)] [animation-duration:2.6s]" />
      )}
    </span>
  );
}
