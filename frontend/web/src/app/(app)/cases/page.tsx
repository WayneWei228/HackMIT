import { CasesHeader } from "./_components/cases-header";
import { CasesWorkspace } from "./_components/cases-workspace";

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
export default function CasesPage() {
  return (
    <main className="flex min-w-[900px] flex-1 flex-col overflow-hidden leading-[normal]">
      <CasesHeader />
      <CasesWorkspace />
    </main>
  );
}
