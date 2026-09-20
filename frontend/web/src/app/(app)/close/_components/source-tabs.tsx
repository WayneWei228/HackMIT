"use client";

import { useEffect, useRef, useState } from "react";
import { motion } from "motion/react";

import { cn } from "@/lib/cn";
import { ChevronDownIcon, SearchIcon } from "@/components/ui/icons";
import { transitions } from "@/lib/motion";

import { SOURCE_TABS, type TabId } from "../_data";
import { TabGlyphIcon } from "./close-icons";

/**
 * The strip of source filters.
 *
 * It scrolls horizontally rather than wrapping, and the comp fades its right
 * edge only while there is something still off-screen - so the overflow is
 * measured rather than assumed.
 */
export function SourceTabs({
  value,
  onChange,
}: {
  value: TabId;
  onChange: (id: TabId) => void;
}) {
  const scroller = useRef<HTMLDivElement>(null);
  const [overflowing, setOverflowing] = useState(false);

  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    const measure = () =>
      setOverflowing(el.scrollWidth - el.clientWidth > 4);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <div className="flex items-center gap-2.5 pb-3 text-muted">
      <div
        ref={scroller}
        className={cn(
          "scrollbar-none flex min-w-0 flex-1 items-center gap-[3px] overflow-x-auto overflow-y-hidden pb-px",
          overflowing &&
            // Safari still needs the prefixed property for the fade-out.
            "[mask-image:linear-gradient(to_right,#000_calc(100%-36px),rgba(0,0,0,0))]",
            "[-webkit-mask-image:linear-gradient(to_right,#000_calc(100%-36px),rgba(0,0,0,0))]",
        )}
      >
        {SOURCE_TABS.map((tab) => {
          const active = tab.id === value;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => onChange(tab.id)}
              className={cn(
                "relative flex flex-none cursor-pointer items-center gap-2 rounded-xl border border-transparent bg-transparent px-3 py-2 text-sm leading-none whitespace-nowrap transition-colors duration-[160ms] ease-[var(--ease-out-soft)]",
                active
                  ? "font-medium text-ink"
                  : "font-normal text-muted hover:bg-wash",
              )}
            >
              {active && (
                <motion.span
                  layoutId="source-tab-pill"
                  transition={transitions.spring}
                  className="absolute -inset-px rounded-xl border border-line-soft bg-panel shadow-[var(--shadow-tab)]"
                />
              )}
              <TabGlyphIcon
                glyph={tab.glyph}
                className={cn(
                  "relative z-10 flex-none",
                  tab.glyph === "sources" ? "text-[#4E7D5C]" : "text-faint-2",
                )}
              />
              <span className="relative z-10">{tab.label}</span>
            </button>
          );
        })}
      </div>

      <div className="flex flex-none items-center gap-0.5">
        <button
          type="button"
          aria-label="Search sources"
          className="flex h-8 w-[34px] cursor-pointer items-center justify-center rounded-xl border border-transparent bg-transparent text-muted-5 transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-wash"
        >
          <SearchIcon size={16} />
        </button>
        <button
          type="button"
          className="flex cursor-pointer items-center gap-[7px] rounded-xl border border-transparent bg-transparent px-2.5 py-2 text-sm leading-none whitespace-nowrap text-muted transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-wash"
        >
          Sort: Relevance
          <ChevronDownIcon size={11} className="text-faint-2" />
        </button>
      </div>
    </div>
  );
}
