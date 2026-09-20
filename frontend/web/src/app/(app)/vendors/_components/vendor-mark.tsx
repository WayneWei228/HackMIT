import { cn } from "@/lib/cn";
import { MARKS, type Vendor } from "../_data";

/**
 * A vendor's brand mark: initials set on the vendor's assigned tint. The comp
 * carries no logo artwork, so the tint plus the initials is the whole mark.
 *
 * Sizes are the comp's three: 34px in a table row, 44px in the rail header,
 * 30px on the collapsed spine. Only the first two carry the 0.02em tracking.
 */
const VARIANTS = {
  row: "h-[34px] w-[34px] rounded-xl text-meta tracking-[0.02em]",
  rail: "h-11 w-11 rounded-[10px] text-lead tracking-[0.02em]",
  mini: "h-[30px] w-[30px] rounded-lg text-[11.5px]",
} as const;

export function VendorMark({
  vendor,
  variant = "row",
  className,
}: {
  vendor: Vendor;
  variant?: keyof typeof VARIANTS;
  className?: string;
}) {
  // A live vendor may carry a mark index the palette does not reach.
  const mark = MARKS[vendor.mark] ?? MARKS[0];
  return (
    <span
      aria-hidden="true"
      className={cn(
        "flex flex-none items-center justify-center font-semibold",
        VARIANTS[variant],
        className,
      )}
      style={{ background: mark.bg, color: mark.fg }}
    >
      {vendor.initials}
    </span>
  );
}
