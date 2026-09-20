"use client";

import { LoadingRows, Skeleton } from "@/components/ui/screen-state";

/**
 * The frame a close screen keeps while it has nothing to put in it.
 *
 * Loading and empty states sit inside the same `<main>` the real screen uses,
 * so the shell does not jump when the answer arrives.
 */
export function ScreenShell({
  loading = false,
  children,
}: {
  loading?: boolean;
  children?: React.ReactNode;
}) {
  return (
    <main className="flex min-w-[820px] flex-1 flex-col overflow-hidden leading-[normal]">
      <div className="flex-none px-[34px] pt-[26px]">
        <Skeleton className="h-[13px] w-[180px]" />
        <Skeleton className="mt-4 h-[46px] w-[320px]" delay={0.05} />
        <Skeleton className="mt-2.5 h-[30px] w-[220px]" delay={0.1} />
      </div>

      <div className="mt-[26px] h-px flex-none bg-line" />

      <div className="min-h-0 flex-1 overflow-y-auto px-[34px] pt-[26px] pb-[26px]">
        {loading ? <LoadingRows rows={5} /> : children}
      </div>
    </main>
  );
}
