import { cn } from "@/lib/cn";

/** A result panel held back until the checks before it have been revealed. It names nothing the agent has not shown. */
export function Awaiting({ title, className }: { title: string; className?: string }) {
  return (
    <section
      className={cn(
        "min-h-[180px] rounded-xl border border-divider bg-panel p-5 shadow-[var(--shadow-tile)]",
        className,
      )}
    >
      <div className="font-display text-2xl leading-[normal] text-ink-deep">{title}</div>
      <div className="mt-4 flex items-center gap-2.5 text-ui text-faint-2">
        <span aria-hidden="true" className="h-[7px] w-[7px] flex-none animate-pulse rounded-full bg-accent" />
        Waiting for the checks above to finish
      </div>
    </section>
  );
}
