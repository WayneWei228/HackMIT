"use client";

import { Suspense } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";
import { useHealth } from "@/lib/use-health";
import { PeriodMenu } from "./period-menu";
import {
  ChevronDownIcon,
  DocIcon,
  HomeIcon,
  InsightsIcon,
  SettingsIcon,
  VendorsIcon,
} from "@/components/ui/icons";

type NavLeaf = { label: string; href?: string };

/**
 * A leaf with no `href` has no screen behind it yet.
 *
 * The product holds no content of its own, so a nav item that would open an
 * invented screen is shown as unavailable rather than wired to a fixture.
 */
const CLOSE_CHILDREN: NavLeaf[] = [
  { label: "Active cases", href: "/close" },
  { label: "All cases", href: "/cases" },
  { label: "Journals", href: routes.journals },
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
  const unavailable = !href && !trailing;
  const className = cn(
    rowBase,
    "gap-3 px-2.5 py-2 text-nav",
    unavailable
      ? "cursor-default text-ghost-2"
      : active
        ? "cursor-pointer text-ink"
        : "cursor-pointer text-ink-2 hover:bg-hover hover:text-ink",
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
    <div className={className} aria-disabled={unavailable || undefined}>
      {body}
    </div>
  );
}

function LeafRow({ item, active }: { item: NavLeaf; active: boolean }) {
  // The comp marks the active leaf with nothing but the green wash: same 42px
  // text indent as its siblings, so switching rows never shifts the label.
  const className = cn(
    rowBase,
    "py-[7px] pr-2.5 pl-[42px] text-body",
    item.href
      ? active
        ? "cursor-pointer bg-accent-soft text-ink"
        : "cursor-pointer text-muted hover:bg-hover hover:text-ink"
      : "cursor-default text-ghost-2",
  );
  return item.href ? (
    <Link href={item.href} className={className}>
      {item.label}
    </Link>
  ) : (
    <div className={className} aria-disabled="true">
      {item.label}
    </div>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  /* Whose books these are, and whether the backend is answering at all. */
  const health = useHealth();
  const isCloseSection =
    pathname.startsWith("/close") ||
    pathname.startsWith("/cases") ||
    pathname.startsWith(routes.journals) ||
    pathname.startsWith("/agents");

  return (
    <aside className="flex w-[232px] flex-none flex-col border-r border-line bg-rail pt-[22px] pb-[18px]">
      {/* The wordmark had a search glyph beside it that searched nothing.
          There is no search endpoint, so there is no search. */}
      <div className="px-5 pb-6">
        <div className="text-ui font-semibold tracking-brand text-ink">
          TRUEUP
        </div>
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
                : item.href === routes.journals
                  ? pathname.startsWith(routes.journals)
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
        <TopRow
          icon={<DocIcon />}
          label="Documents"
          href={routes.documents}
          active={pathname.startsWith(routes.documents)}
        />
        <TopRow icon={<InsightsIcon />} label="Insights" />
        <TopRow icon={<SettingsIcon />} label="Settings" />
      </nav>

      <div className="flex-1" />

      <div className="px-3">
        <div className="mx-2 mb-4 h-px bg-line-warm" />

        {/* The menu reads the month out of the URL, which suspends during
            the static prerender - and the sidebar sits above every page's
            own boundary, so it carries one of its own. */}
        <Suspense fallback={<PeriodMenuPlaceholder />}>
          <PeriodMenu />
        </Suspense>

        {/* No user block: the backend has no user concept, and a name here
            would be the one piece of content this product invented. What it
            does know is which company's books these are, and whether it can
            reach them at all. */}
        <div className="mt-1 flex items-center gap-2.5 px-2.5 pt-2.5 pb-1">
          <ConnectionDot state={health.state} />
          <div className="min-w-0 flex-1">
            <div className="truncate text-body text-ink">
              {health.company ?? "Close workspace"}
            </div>
            <div className="mt-0.5 truncate text-meta text-faint-2">
              {health.state === "connected"
                ? "Connected"
                : health.state === "offline"
                  ? "Backend not reachable"
                  : "Connecting..."}
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
}

/** Whether the close API is answering: the app's only always-on indicator. */
function ConnectionDot({ state }: { state: "connecting" | "connected" | "offline" }) {
  return (
    <span className="relative h-2 w-2 flex-none" aria-hidden="true">
      <span
        className={cn(
          "absolute inset-0 rounded-full transition-colors duration-[400ms] ease-[var(--ease-out-soft)]",
          state === "connected"
            ? "bg-accent"
            : state === "offline"
              ? "bg-[#C08A5A]"
              : "bg-rule",
        )}
      />
      {state === "connected" ? (
        <span className="animate-pulse-ring absolute -inset-1 rounded-full border-[1.2px] border-[rgba(46,128,71,0.5)] [animation-duration:2.6s]" />
      ) : null}
    </span>
  );
}

/** The period chip's own footprint, held while the URL is still unknown. */
function PeriodMenuPlaceholder() {
  return (
    <div className="flex items-center gap-2.5 rounded-lg px-2.5 py-1.5">
      <div className="min-w-0 flex-1">
        <div className="h-[15px] w-[108px] rounded-md bg-wash-cool" />
        <div className="mt-1.5 h-[11px] w-[74px] rounded-md bg-wash-cool" />
      </div>
    </div>
  );
}
