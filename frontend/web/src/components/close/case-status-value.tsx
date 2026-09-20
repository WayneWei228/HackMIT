import type { CaseStatus } from "@/lib/api-types";
import { STATUS_STYLES } from "@/lib/status-styles";

/** The status figure in a case header: a dot in the status colour, then the word. */
export function CaseStatusValue({
  status,
  className = "text-[24px]",
}: {
  status: CaseStatus;
  className?: string;
}) {
  const { dot } = STATUS_STYLES[status];
  return (
    <span className="flex items-center gap-2.5">
      <span
        className="h-[9px] w-[9px] flex-none rounded-full"
        style={{ background: dot }}
      />
      <span className={`font-display leading-none text-ink-deep ${className}`}>
        {status}
      </span>
    </span>
  );
}
