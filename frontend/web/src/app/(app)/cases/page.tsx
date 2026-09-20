import { Suspense } from "react";

import { CasesRoute } from "./_components/cases-route";
import { CasesScreen } from "./_components/cases-screen";

export const metadata = {
  title: "All cases - TrueUp",
};

/**
 * Case management: every vendor close workflow in the selected month's close.
 * The shell and sidebar come from `(app)/layout.tsx`.
 *
 * The month lives in `?period=`, so the component that reads it sits under a
 * `Suspense` boundary - `useSearchParams` suspends during the prerender, and
 * the fallback is the same screen with no month, which resolves to whatever
 * the backend calls current.
 *
 * `leading-[normal]` restores the comp's inherited line-height. Tailwind's
 * preflight puts `line-height: 1.5` on `html`, which the comps never had, and
 * that pushed every unleaded run of text - breadcrumb, subtitle, table cells,
 * stat captions - about 13px down the page. Belongs on `body` in globals.css;
 * see the report.
 */
export default function CasesPage() {
  return (
    <main className="flex min-w-[900px] flex-1 flex-col overflow-hidden leading-[normal]">
      <Suspense fallback={<CasesScreen periodParam={null} />}>
        <CasesRoute />
      </Suspense>
    </main>
  );
}
