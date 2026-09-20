import Link from "next/link";
import type { ReactNode } from "react";

import { Breadcrumb, PageSubtitle, PageTitle } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import { periodLabel } from "@/lib/time";

export function ReportFrame({ title, description, children, toolbar }: {
  title: string; description: string; children: ReactNode; toolbar?: ReactNode;
}) {
  return (
    <main className="flex min-w-[900px] flex-1 flex-col overflow-hidden">
      <header className="flex-none border-b border-line px-[34px] pt-[26px] pb-5">
        <Breadcrumb items={[{ label: "CLOSE", href: "/cases" }, { label: title.toUpperCase() }]} />
        <PageTitle className="text-[46px]/[1.05]">{title}</PageTitle>
        <PageSubtitle>{description}</PageSubtitle>
        {toolbar}
      </header>
      <div className="min-h-0 flex-1 overflow-auto px-[34px] py-6">{children}</div>
    </main>
  );
}

export function MonthLinks({ months, selected, href, all = true, param = "period" }: {
  months: string[]; selected?: string | null; href: string; all?: boolean; param?: string;
}) {
  const options = [...(all ? [""] : []), ...months];
  const pathFor = (month: string) => {
    const [path, query] = href.split("?", 2);
    const params = new URLSearchParams(query);
    if (month) params.set(param, month); else params.delete(param);
    return `${path}${params.size ? `?${params}` : ""}`;
  };
  return (
    <nav aria-label="Reporting month" className="mt-5 flex flex-wrap gap-2">
      {options.map((month) => <Link key={month} href={pathFor(month)}
        aria-current={(selected || "") === month ? "page" : undefined}
        className={cn("rounded-md border px-3 py-1.5 text-sm", (selected || "") === month
          ? "border-accent-line bg-accent-soft text-accent-deep" : "border-line text-muted hover:bg-wash")}>
        {month ? periodLabel(month) : "All months"}
      </Link>)}
    </nav>
  );
}

export function EmptyReport({ children }: { children: ReactNode }) {
  return <div className="rounded-xl border border-dashed border-line p-10 text-center text-muted">{children}</div>;
}

export function tokenLabel(value: string) {
  return value.replaceAll("_", " ").replaceAll("-", " ").toLowerCase();
}
