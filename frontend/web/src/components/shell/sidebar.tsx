"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { ClockTimeline } from "@/components/shell/clock-timeline";
import type { CloseView } from "@/lib/api-types";
import { cn } from "@/lib/cn";
import {
  ChevronDownIcon,
  ChevronRightIcon,
  DocIcon,
  HomeIcon,
  InsightsIcon,
  MoreIcon,
  SearchIcon,
  SettingsIcon,
  VendorsIcon,
} from "@/components/ui/icons";

type NavLeaf = { label: string; href?: string };

const CLOSE_CHILDREN: NavLeaf[] = [
  { label: "Active cases", href: "/close" },
  { label: "All cases", href: "/cases" },
  { label: "Learning", href: "/learning" },
  { label: "Journals" },
  { label: "Reconciliations" },
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
};

const FALLBACK_IDENTITY: SidebarIdentity = {
  periodLabel: "December 2026",
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
  const pathname = usePathname();
  const isCloseSection =
    pathname.startsWith("/close") ||
    pathname.startsWith("/cases") ||
    pathname.startsWith("/learning") ||
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
        <button
          type="button"
          aria-label="Search"
          className="text-muted-5 transition-colors duration-[160ms] hover:text-ink"
        >
          <SearchIcon />
        </button>
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
            item={item}
            active={
              item.href === "/cases"
                ? pathname === "/cases"
                : item.href === "/learning"
                  ? pathname.startsWith("/learning")
                  : item.href === "/close"
                  ? pathname.startsWith("/close") || pathname.startsWith("/agents")
                  : false
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
        <TopRow icon={<DocIcon />} label="Documents" />
        <TopRow icon={<InsightsIcon />} label="Insights" />
        <TopRow icon={<SettingsIcon />} label="Settings" />
      </nav>

      <div className="flex-1" />

      <ClockTimeline initial={close} />

      <div className="px-3">
        <div className="mx-2 mb-4 h-px bg-line-warm" />
        <div className="flex cursor-pointer items-center gap-2.5 rounded-lg px-2.5 py-1.5 transition-colors duration-[160ms] hover:bg-hover">
          <div className="flex-1">
            <div className="text-body text-ink">{identity.periodLabel}</div>
            <div className="mt-0.5 text-meta text-faint-2">Controller</div>
          </div>
          <ChevronRightIcon className="text-faint-2" />
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
