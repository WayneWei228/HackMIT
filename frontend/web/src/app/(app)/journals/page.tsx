import { Suspense } from "react";

import { JournalsRoute } from "./_components/journals-route";
import { JournalsScreen } from "./_components/journals-screen";

export const metadata = {
  title: "Journals - TrueUp",
};

/**
 * The journal entries the close posted for the selected month. The shell and
 * sidebar come from `(app)/layout.tsx`.
 *
 * The month lives in `?period=`, so the component that reads it sits under a
 * `Suspense` boundary - `useSearchParams` suspends during the prerender, and
 * the fallback is the same screen with no month, which resolves to whatever
 * the backend calls current.
 *
 * `leading-[normal]` restores the comp's inherited line-height, the same way
 * the cases page does.
 */
export default function JournalsPage() {
  return (
    <main className="flex min-w-[900px] flex-1 flex-col overflow-hidden leading-[normal]">
      <Suspense fallback={<JournalsScreen periodParam={null} />}>
        <JournalsRoute />
      </Suspense>
    </main>
  );
}
