"use client";

import { useRouter } from "next/navigation";
import { motion } from "motion/react";

import { Button } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import { riseIn, staggerParent, transitions } from "@/lib/motion";

/**
 * What a screen shows when it has no rows to show.
 *
 * The product holds no content of its own: every number, name and sentence
 * comes from the close backend. So "nothing here" is an ordinary state, not a
 * failure, and it has three flavours worth telling apart - the backend has
 * not run this month yet, the backend cannot be reached at all, and the thing
 * you asked for does not exist. All three are the same quiet paper block:
 * a dashed hairline rule, a serif line, and one sentence saying what would
 * fill it.
 */
export type ScreenStateAction = {
  label: string;
  onClick?: () => void;
  href?: string;
};

export function ScreenState({
  tone = "empty",
  title,
  body,
  detail,
  actions,
  className,
}: {
  tone?: "empty" | "error";
  title: string;
  body?: string;
  /** A URL, a backend message - set in the monospace-ish meta tone. */
  detail?: string | null;
  actions?: ScreenStateAction[];
  className?: string;
}) {
  const router = useRouter();

  return (
    <motion.div
      variants={staggerParent(0.045)}
      initial="hidden"
      animate="visible"
      className={cn(
        "flex flex-col items-center gap-3.5 rounded-xl border border-dashed px-6 py-[42px] text-center",
        tone === "error" ? "border-[#D9CBBF]" : "border-line",
        className,
      )}
    >
      <motion.div
        variants={riseIn}
        className="font-display text-2xl leading-[1.2] text-ink-deep"
      >
        {title}
      </motion.div>

      {body ? (
        <motion.p
          variants={riseIn}
          className="max-w-[440px] text-body leading-[1.6] text-pretty text-faint"
        >
          {body}
        </motion.p>
      ) : null}

      {detail ? (
        <motion.div
          variants={riseIn}
          className="max-w-[440px] text-meta leading-[1.6] break-all text-ghost"
        >
          {detail}
        </motion.div>
      ) : null}

      {actions && actions.length > 0 ? (
        <motion.div
          variants={riseIn}
          className="mt-1 flex flex-wrap items-center justify-center gap-2.5"
        >
          {actions.map((action, i) => (
            <Button
              key={action.label}
              variant={i === 0 ? "primary" : "secondary"}
              onClick={() => {
                if (action.href) router.push(action.href);
                action.onClick?.();
              }}
              className="text-[13.5px]/[1]"
            >
              {action.label}
            </Button>
          ))}
        </motion.div>
      ) : null}
    </motion.div>
  );
}

/**
 * The backend is not answering.
 *
 * Named so the reader can act on it: the URL the app is configured with is
 * the one thing that tells them whether the API is down or the app is
 * pointed at the wrong place.
 */
export function BackendUnreachable({
  url,
  error,
  onRetry,
  className,
}: {
  url: string | null;
  error?: string | null;
  onRetry: () => void;
  className?: string;
}) {
  return (
    <ScreenState
      tone="error"
      title="Backend not reachable"
      body="Every figure in this product comes from the close API, so there is nothing to show until it answers."
      detail={[url, error].filter(Boolean).join(" · ") || null}
      actions={[{ label: "Try again", onClick: onRetry }]}
      className={className}
    />
  );
}

/** A soft block standing in for content that has not arrived yet. */
export function Skeleton({
  className,
  delay = 0,
}: {
  className?: string;
  delay?: number;
}) {
  return (
    <motion.div
      aria-hidden="true"
      initial={{ opacity: 0.45 }}
      animate={{ opacity: [0.45, 0.8, 0.45] }}
      transition={{
        duration: 1.6,
        ease: "easeInOut",
        repeat: Infinity,
        delay,
      }}
      className={cn("rounded-md bg-wash-cool", className)}
    />
  );
}

/** A page-sized wait: a few rows of skeleton in the content column. */
export function LoadingRows({
  rows = 6,
  className,
}: {
  rows?: number;
  className?: string;
}) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={transitions.base}
      className={cn("flex flex-col gap-2.5", className)}
    >
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-[54px] w-full" delay={i * 0.08} />
      ))}
    </motion.div>
  );
}
