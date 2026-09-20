"use client";

import Link from "next/link";
import { motion } from "motion/react";
import type { ComponentProps, ReactNode } from "react";

import { cn } from "@/lib/cn";
import { SearchIcon, SortIcon } from "@/components/ui/icons";
import { riseIn, staggerParent, transitions } from "@/lib/motion";

/* -------------------------------------------------------------------------- */
/* Page chrome                                                                 */
/* -------------------------------------------------------------------------- */

export function Breadcrumb({
  items,
}: {
  items: { label: string; href?: string }[];
}) {
  return (
    <div className="flex items-center gap-2 text-eyebrow font-medium tracking-caps-xl text-faint-2">
      {items.map((item, i) => (
        <span key={item.label} className="flex items-center gap-2">
          {i > 0 && <span aria-hidden="true">/</span>}
          {item.href ? (
            <Link
              href={item.href}
              className="text-faint-2 transition-colors duration-[160ms] hover:text-ink"
            >
              {item.label}
            </Link>
          ) : (
            <span className="text-ink">{item.label}</span>
          )}
        </span>
      ))}
    </div>
  );
}

export function PageTitle({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <motion.h1
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={transitions.slow}
      className={cn(
        "font-display mt-3 text-display leading-[1.05] tracking-display text-ink-deep",
        className,
      )}
    >
      {children}
    </motion.h1>
  );
}

export function PageSubtitle({ children }: { children: ReactNode }) {
  return (
    <p className="mt-2.5 text-lead text-muted-4 text-pretty">{children}</p>
  );
}

/* -------------------------------------------------------------------------- */
/* Controls                                                                    */
/* -------------------------------------------------------------------------- */

const buttonBase =
  "flex items-center gap-2.5 rounded-xl whitespace-nowrap cursor-pointer transition-colors duration-[160ms] ease-[var(--ease-out-soft)] focus-visible:outline-none focus-visible:shadow-[var(--shadow-ring)]";

export function Button({
  variant = "secondary",
  className,
  ...props
}: ComponentProps<"button"> & { variant?: "primary" | "secondary" | "solid" }) {
  return (
    <button
      type="button"
      className={cn(
        buttonBase,
        variant === "primary" &&
          "border border-accent bg-panel px-4 py-[11px] text-ui font-medium leading-none text-accent hover:bg-accent hover:text-accent-on",
        variant === "secondary" &&
          "border border-line-soft bg-panel px-3.5 py-[11px] text-ui leading-none text-ink-2 hover:bg-panel-hover",
        variant === "solid" &&
          "bg-accent px-4 py-[11px] text-ui font-medium leading-none text-accent-on hover:bg-accent-press",
        className,
      )}
      {...props}
    />
  );
}

export function SearchField({
  className,
  ...props
}: ComponentProps<"input">) {
  return (
    <div className={cn("relative min-w-[220px] flex-1 max-w-[420px]", className)}>
      <SearchIcon
        size={16}
        className="pointer-events-none absolute left-[13px] top-1/2 -translate-y-1/2 text-faint-3"
      />
      <input
        className="w-full rounded-xl border border-line-soft bg-panel py-[11px] pr-[13px] pl-[38px] text-body leading-[1.2] text-ink outline-none transition-[border-color,box-shadow] duration-[160ms] ease-[var(--ease-out-soft)] focus:border-[#B8C7B5] focus:shadow-[var(--shadow-ring-soft)]"
        {...props}
      />
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Data display                                                                */
/* -------------------------------------------------------------------------- */

export type Stat = { value: ReactNode; label: string };

/** The divided run of serif numerals that sits beside a page's filter row. */
export function StatStrip({
  stats,
  size = 27,
  className,
}: {
  stats: Stat[];
  size?: number;
  className?: string;
}) {
  return (
    <motion.div
      variants={staggerParent(0.05)}
      initial="hidden"
      animate="visible"
      className={cn("flex flex-none items-stretch", className)}
    >
      {stats.map((stat, i) => (
        <motion.div
          key={stat.label}
          variants={riseIn}
          className={cn(
            "px-[22px]",
            i === 0 && "pl-0",
            i === stats.length - 1 && "pr-0",
            i > 0 && "border-l border-line",
          )}
        >
          <div
            className="font-display leading-none text-ink-deep"
            style={{ fontSize: size }}
          >
            {stat.value}
          </div>
          <div className="mt-[7px] text-meta text-faint">{stat.label}</div>
        </motion.div>
      ))}
    </motion.div>
  );
}

/** A soft rounded tag - workflow names, treatments, statuses. */
export function Tag({
  children,
  tone = "neutral",
  className,
}: {
  children: ReactNode;
  tone?: "neutral" | "accent" | "cool" | "warm";
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md px-2.5 py-1.5 text-meta whitespace-nowrap",
        tone === "neutral" && "bg-wash text-ink-2",
        tone === "accent" && "bg-accent-soft text-accent-press",
        tone === "cool" && "bg-[#EDF0F4] text-[#3D4A57]",
        tone === "warm" && "bg-[#F5EFE4] text-[#6B5A3C]",
        className,
      )}
    >
      {children}
    </span>
  );
}

/*
 * The comps' five status tones, verbatim. The pulse ring is always the same
 * green hairline whatever the dot underneath it is - it signals "live", not
 * status - so it is not part of this map.
 */
const DOT_TONES = {
  running: "bg-[#63A644]",
  progress: "bg-[#9AA096]",
  queued: "bg-[#C0C5BB]",
  ready: "bg-[#2E8047]",
  complete: "bg-[#1F5132]",
} as const;

export type DotTone = keyof typeof DOT_TONES;

export function StatusDot({
  tone = "queued",
  pulse = false,
  className,
}: {
  tone?: DotTone;
  pulse?: boolean;
  className?: string;
}) {
  return (
    <span
      className={cn("relative h-2 w-2 flex-none", className)}
      aria-hidden="true"
    >
      <span className={cn("absolute inset-0 rounded-full", DOT_TONES[tone])} />
      {pulse && (
        <span className="animate-pulse-ring absolute -inset-1 rounded-full border-[1.2px] border-[rgba(46,128,71,0.5)]" />
      )}
    </span>
  );
}

/** Pill-shaped filter tabs with a shared sliding background. */
export function TabRow<T extends string>({
  tabs,
  value,
  onChange,
  layoutId = "tab-pill",
}: {
  tabs: { id: T; label: string; count?: number }[];
  value: T;
  onChange: (id: T) => void;
  layoutId?: string;
}) {
  return (
    <div className="scrollbar-none mt-[22px] flex items-center gap-0.5 overflow-x-auto">
      {tabs.map((tab) => {
        const active = tab.id === value;
        return (
          <button
            key={tab.id}
            type="button"
            onClick={() => onChange(tab.id)}
            className={cn(
              "relative flex flex-none items-center gap-[9px] rounded-xl border border-transparent px-3.5 py-[9px] text-ui leading-none whitespace-nowrap transition-colors duration-[160ms] ease-[var(--ease-out-soft)]",
              active
                ? "font-medium text-ink"
                : "text-muted hover:bg-wash hover:text-ink",
            )}
          >
            {active && (
              <motion.span
                layoutId={layoutId}
                transition={transitions.spring}
                className="absolute inset-0 -z-0 rounded-xl border border-accent-line-3 bg-accent-soft"
              />
            )}
            <span className="relative z-10">{tab.label}</span>
            {tab.count !== undefined && (
              <span
                className={cn(
                  "relative z-10 text-meta tabular-nums transition-colors duration-[160ms]",
                  active ? "text-accent-moss" : "text-ghost",
                )}
              >
                {tab.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

export type SortDir = "asc" | "desc";

/** A clickable column heading with the comps' two-triangle sort glyph. */
export function ColumnHeader({
  label,
  active,
  dir,
  align = "left",
  onClick,
}: {
  label: string;
  active?: boolean;
  dir?: SortDir;
  align?: "left" | "right";
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex cursor-pointer items-center gap-[7px] text-eyebrow font-medium tracking-[0.12em] select-none transition-colors duration-[160ms] hover:text-ink",
        active ? "text-ink" : "text-faint",
        align === "right" && "justify-end",
      )}
    >
      {label}
      <svg width="10" height="12" viewBox="0 0 10 12" fill="none" className="flex-none">
        <path
          d="M5 1.6L7.4 4.4H2.6z"
          fill={active && dir === "asc" ? "var(--color-accent)" : "var(--color-rule)"}
        />
        <path
          d="M5 10.4L2.6 7.6h4.8z"
          fill={active && dir === "desc" ? "var(--color-accent)" : "var(--color-rule)"}
        />
      </svg>
    </button>
  );
}

export { SortIcon };

/** The small uppercase label that opens a section in the detail rails. */
export function SectionLabel({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "text-eyebrow font-medium tracking-caps-lg text-faint-2 uppercase",
        className,
      )}
    >
      {children}
    </div>
  );
}

/** Serif section heading used inside detail rails. */
export function RailHeading({ children }: { children: ReactNode }) {
  return (
    <h2 className="font-display text-lg leading-none text-ink-deep">
      {children}
    </h2>
  );
}
