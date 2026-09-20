"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { ClockTimeline } from "@/components/shell/clock-timeline";
import type { CloseView } from "@/lib/api-types";
import { cn } from "@/lib/cn";
import type { PeriodsView } from "@/lib/report-types";
import { periodLabel } from "@/lib/time";
import {
  ChevronDownIcon,
  DocIcon,
  HomeIcon,
  InsightsIcon,
  MoreIcon,
  SettingsIcon,
  VendorsIcon,
} from "@/components/ui/icons";

type NavLeaf = { label: string; href?: string };

const CLOSE_CHILDREN: NavLeaf[] = [
  { label: "Active cases", href: "/close" },
  { label: "All cases", href: "/cases" },
  { label: "Learning", href: "/learning" },
  { label: "Journals", href: "/journals" },
  { label: "Vendor stories", href: "/close/story" },
];

const rowBase =
  "flex items-center rounded-lg transition-colors duration-[160ms] ease-[var(--ease-out-soft)]";

function TopRow({
  icon,
  label,
  href,
  active,
  trailing,
}: {
  icon: React.ReactNode;
  label: string;
  href?: string;
  active?: boolean;
  trailing?: React.ReactNode;
}) {
  const className = cn(
    rowBase,
    "gap-3 px-2.5 py-2 text-nav cursor-pointer",
    active ? "text-ink" : "text-ink-2 hover:bg-hover hover:text-ink",
  );
  const body = (
    <>
      <span className="flex-none text-muted-2">{icon}</span>
      <span className="flex-1">{label}</span>
      {trailing}
    </>
  );
  return href ? (
    <Link href={href} className={className}>
      {body}
    </Link>
  ) : (
    <div className={className}>{body}</div>
  );
}

function LeafRow({ item, active }: { item: NavLeaf; active: boolean }) {
  // The comp marks the active leaf with nothing but the green wash: same 42px
  // text indent as its siblings, so switching rows never shifts the label.
  const className = cn(
    rowBase,
    "py-[7px] pr-2.5 pl-[42px] text-body cursor-pointer",
    active ? "bg-accent-soft text-ink" : "text-muted hover:bg-hover hover:text-ink",
  );
  return item.href ? (
    <Link href={item.href} className={className}>
      {item.label}
    </Link>
  ) : (
    <div className={className}>{item.label}</div>
  );
}

export type SidebarIdentity = {
  periodLabel: string;
  controllerName: string;
  controllerRole: string;
  calendar?: PeriodsView;
};

const FALLBACK_IDENTITY: SidebarIdentity = {
  periodLabel: "",
  controllerName: "Controller",
  controllerRole: "Backend offline",
};

export function Sidebar({
  identity = FALLBACK_IDENTITY,
  close = null,
}: {
  identity?: SidebarIdentity;
  /** The close as the server read it; the timeline keeps itself fresh after that. */
  close?: CloseView | null;
}) {
  /* The month in the URL is read below, which needs a Suspense boundary of its own. */
  return <Suspense fallback={<aside className="w-[232px] flex-none border-r border-line bg-rail" />}>
    <SidebarContent identity={identity} close={close} />
  </Suspense>;
}

function SidebarContent({
  identity,
  close,
}: {
  identity: SidebarIdentity;
  close: CloseView | null;
}) {
  const pathname = usePathname();
  const params = useSearchParams();
  const router = useRouter();
  const period = params.get("period");
  const withPeriod = (href: string) => period && ["/cases", "/journals", "/documents"].includes(href)
    ? `${href}?period=${encodeURIComponent(period)}` : href;
  const isCloseSection =
    pathname.startsWith("/close") ||
    pathname.startsWith("/cases") ||
    pathname.startsWith("/learning") ||
    pathname.startsWith("/journals") ||
    pathname.startsWith("/agents");
  const initials = identity.controllerName
    .split(" ")
    .map((word) => word[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  return (
    <aside className="flex w-[232px] flex-none flex-col border-r border-line bg-rail pt-[22px] pb-[18px]">
      <div className="flex items-center justify-between px-5 pb-6">
        <div className="text-ui font-semibold tracking-brand text-ink">
          TRUEUP
        </div>
        {/* The comp's "Search" action opened a search screen that has no
            backend behind it, so it is not drawn: an affordance that leads
            nowhere is worse than none. */}
      </div>

      <nav className="flex flex-col gap-px px-3">
        <TopRow icon={<HomeIcon />} label="Home" href="/" active={pathname === "/"} />
        <TopRow
          icon={<DocIcon />}
          label="Close"
          active={isCloseSection}
          trailing={
            <ChevronDownIcon className="text-faint-2" />
          }
        />
        {CLOSE_CHILDREN.map((item) => (
          <LeafRow
            key={item.label}
            item={{ ...item, href: item.href ? withPeriod(item.href) : undefined }}
            active={
              item.href === "/cases"
                ? pathname === "/cases"
                : item.href === "/learning"
                  ? pathname.startsWith("/learning")
                  : item.href === "/close"
                  ? (pathname.startsWith("/close") && pathname !== "/close/story") || pathname.startsWith("/agents")
                  : pathname === item.href
            }
          />
        ))}

        <div className="h-[18px]" />

        <TopRow
          icon={<VendorsIcon />}
          label="Vendors"
          href="/vendors"
          active={pathname.startsWith("/vendors")}
        />
        <TopRow icon={<DocIcon />} label="Documents" href={withPeriod("/documents")} active={pathname === "/documents"} />
        <TopRow icon={<InsightsIcon />} label="Insights" />
        <TopRow icon={<SettingsIcon />} label="Settings" />
      </nav>

      <div className="flex-1" />

      <ClockTimeline initial={close} />

      <div className="px-3">
        <div className="mx-2 mb-4 h-px bg-line-warm" />
        <div className="flex items-center gap-2.5 rounded-lg px-2.5 py-1.5">
          <div className="flex-1">
            {identity.calendar ? <label className="block text-xs text-faint-2">Browse month
              <select aria-label="Browse month" className="mt-1 block w-full rounded-md border border-line bg-panel px-2 py-2 text-sm text-ink"
                value={period ?? ""} onChange={(event) => {
                  const path = ["/cases", "/journals", "/documents"].includes(pathname) ? pathname : "/cases";
                  const month = event.target.value;
                  router.push(`${path}${month ? `?period=${encodeURIComponent(month)}` : ""}`);
                }}>
                <option value="">{pathname === "/journals" || pathname === "/documents" ? "All months" : "Active close"}</option>
                {identity.calendar.periods.map((month) => <option key={month} value={month}>{periodLabel(month)}</option>)}
              </select>
            </label> : identity.periodLabel && (
              <div className="text-body text-ink">{identity.periodLabel}</div>
            )}
            <div className="mt-0.5 text-meta text-faint-2">Controller</div>
          </div>
        </div>
        <div className="flex items-center gap-[11px] px-2.5 pt-2.5 pb-1">
          <div className="flex h-[34px] w-[34px] flex-none items-center justify-center rounded-full bg-accent-forest text-micro font-semibold tracking-[0.03em] text-accent-on-2">
            {initials}
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-body text-ink">{identity.controllerName}</div>
            <div className="mt-0.5 text-meta text-faint-2">{identity.controllerRole}</div>
          </div>
          <MoreIcon className="cursor-pointer text-lead text-faint-3" />
        </div>
      </div>
    </aside>
  );
}
