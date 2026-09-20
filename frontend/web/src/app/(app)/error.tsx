"use client";

import { useRouter } from "next/navigation";
import { startTransition } from "react";

import { Button } from "@/components/ui/primitives";

/** The API is down, or answered with an error: say so instead of a blank page. */
export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const router = useRouter();
  const unreachable = /not reachable|fetch failed|Failed to fetch/i.test(error.message);

  return (
    <main className="flex min-w-[760px] flex-1 flex-col items-center justify-center gap-3 px-10">
      <div className="text-eyebrow font-medium tracking-caps-xl text-faint-2">
        {unreachable ? "BACKEND NOT REACHABLE" : "SOMETHING WENT WRONG"}
      </div>
      <div className="font-display text-4xl text-ink-deep">
        {unreachable ? "The TrueUp backend is not running" : "The backend could not answer"}
      </div>
      <p className="max-w-[520px] text-center text-lead text-muted-4 text-pretty">
        {unreachable
          ? "Start it from the backend folder, then try again."
          : "The request reached the backend, but it returned an error."}
      </p>
      <code className="rounded-lg border border-line bg-panel px-3.5 py-2 text-ui text-ink-2">
        {unreachable ? "uv run python scripts/serve.py" : error.message}
      </code>
      <Button
        className="mt-2 text-[13.5px]/[1]"
        onClick={() =>
          startTransition(() => {
            router.refresh();
            reset();
          })
        }
      >
        Try again
      </Button>
    </main>
  );
}
