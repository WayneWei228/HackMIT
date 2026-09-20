"use client";

import { useSearchParams } from "next/navigation";

import { StoryScreen } from "./story-screen";

/** Reads `?vendor=`, `?through=` and `?case=` - kept apart so the page can wrap it in `Suspense`. */
export function StoryRoute() {
  const params = useSearchParams();
  return (
    <StoryScreen
      vendor={params.get("vendor")}
      caseParam={params.get("case")}
      through={params.get("through")}
    />
  );
}
