/**
 * The 10.5px uppercase label that opens each block of the live execution rail.
 *
 * The shared `SectionLabel` is 10.5px on `--color-faint-2`; this rail's labels
 * sit on `--color-faint` (#8A8F86). Recolouring the shared one through `cn`
 * is not an option: `tailwind-merge` reads `text-eyebrow` and `text-faint` as
 * the same `text-*` group and drops the size, so the label silently renders at
 * the inherited 14px. Keeping the classes in one literal avoids the merge.
 */
export function RailLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-eyebrow font-medium tracking-caps-lg text-faint uppercase">
      {children}
    </div>
  );
}
