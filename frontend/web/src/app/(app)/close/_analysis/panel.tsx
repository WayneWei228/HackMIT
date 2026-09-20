import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

/** The white card the three working columns share. */
export function Panel({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <section
      className={cn(
        "min-h-full rounded-xl border border-divider bg-panel shadow-tile",
        className,
      )}
    >
      {children}
    </section>
  );
}

/** 21px serif heading at the top of a column. */
export function PanelHeading({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <h2 className={cn("font-display text-2xl leading-[normal] text-ink-deep", className)}>
      {children}
    </h2>
  );
}
