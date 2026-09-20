import { getClose } from "@/lib/api";

import { CasesHeader } from "./_components/cases-header";
import { CasesWorkspace } from "./_components/cases-workspace";
import { toCaseRecords } from "./_records";

/** Every screen shows live backend state, so nothing here is prerendered at build time. */
export const dynamic = "force-dynamic";

export const metadata = {
  title: "All cases - TrueUp",
};

/**
 * Case management: every vendor close workflow in the December close.
 * The shell and sidebar come from `(app)/layout.tsx`.
 *
 * `leading-[normal]` restores the comp's inherited line-height. Tailwind's
 * preflight puts `line-height: 1.5` on `html`, which the comps never had, and
 * that pushed every unleaded run of text - breadcrumb, subtitle, table cells,
 * stat captions - about 13px down the page. Belongs on `body` in globals.css;
 * see the report.
 */
export default async function CasesPage() {
  const close = await getClose();
  return (
    <main className="flex min-w-[900px] flex-1 flex-col overflow-hidden leading-[normal]">
      <CasesHeader close={close} />
      <CasesWorkspace cases={toCaseRecords(close.cases)} />
    </main>
  );
}
