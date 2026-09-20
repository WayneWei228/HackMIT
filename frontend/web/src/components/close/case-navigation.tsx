"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

import { caseHref } from "@/lib/case-nav";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";

const screens = [
  ["Files", routes.closeCase], ["Evidence", routes.evidence],
  ["Detection", routes.detection], ["Invoice lookup", routes.invoiceLookup],
  ["Classification", routes.classification], ["Estimation", routes.estimation],
  ["Outreach", routes.outreach], ["Settlement", routes.settlement],
  ["Verification", routes.verification], ["Story", routes.story],
] as const;

export function CaseNavigation() {
  const path = usePathname();
  const params = useSearchParams();
  const id = params.get("o");
  return <nav aria-label="Case views" className="flex flex-none gap-4 overflow-x-auto border-b border-line bg-panel px-[34px] py-3">
    {screens.map(([label, href]) => <Link key={href} href={caseHref(href, id)}
      aria-current={path === href ? "page" : undefined}
      className={cn("shrink-0 text-xs", path === href ? "font-semibold text-accent-deep" : "text-muted hover:text-ink")}>
      {label}
    </Link>)}
  </nav>;
}
