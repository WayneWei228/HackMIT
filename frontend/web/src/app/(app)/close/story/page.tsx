import { Suspense } from "react";

import { StoryRoute } from "./_components/story-route";
import { StoryScreen } from "./_components/story-screen";

export const metadata = {
  title: "Case story - TrueUp",
};

/**
 * One vendor, told in the order it happened: what arrived, what each agent made
 * of it, who was asked, what they answered - across all its months, and only
 * up to the end of the month in `?through=`. Everything on it comes from
 * `GET /api/story`.
 *
 * The vendor lives in `?vendor=`, so the component that reads it sits under a
 * `Suspense` boundary - `useSearchParams` suspends during the prerender.
 */
export default function StoryPage() {
  return (
    <main className="flex min-w-[900px] flex-1 flex-col overflow-hidden leading-[normal]">
      <Suspense
        fallback={<StoryScreen vendor={null} caseParam={null} through={null} />}
      >
        <StoryRoute />
      </Suspense>
    </main>
  );
}
