"use client";

import { StatusDot, Tag } from "@/components/ui/primitives";

import { isClean, tokenLabel } from "../_data";

/**
 * Whether the extraction came out clean.
 *
 * A clean document is the norm, so it reads as the norm: the same hairline
 * status dot the rest of the product uses, in the "ready" tone, with the
 * backend's own word beside it. Anything else is an exception and takes the
 * warm pill - the treatment this product already uses for something that
 * wants a second look - so a flagged row is visible while scrolling.
 *
 * Both are existing primitives; nothing new is invented for this column.
 */
export function DocumentQuality({
  quality,
  reasons,
}: {
  quality: string;
  /** The backend's explanation, shown on hover when it sent one. */
  reasons?: string[] | null;
}) {
  const detail = reasons?.length ? reasons.join(" · ") : undefined;
  const label = tokenLabel(quality);

  if (isClean(quality)) {
    return (
      <div className="flex min-w-0 items-center gap-2.5" title={detail}>
        <StatusDot tone="ready" />
        <span className="truncate text-body text-ink-2">{quality}</span>
      </div>
    );
  }

  return (
    <Tag tone="warm" className="max-w-full gap-2">
      <StatusDot tone="progress" />
      <span className="truncate" title={detail ?? label}>
        {label}
      </span>
    </Tag>
  );
}
