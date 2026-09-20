"use client";

import {
  AnimatePresence,
  motion,
  useReducedMotion,
  type Variants,
} from "motion/react";
import { useCallback, useEffect, useRef, useState } from "react";

import { CaretLeftIcon } from "@/components/ui/icons";
import { cn } from "@/lib/cn";
import { crossFade, easeOutSoft, transitions } from "@/lib/motion";
import type { Vendor } from "../_data";
import { VendorDetail } from "./vendor-detail";
import { VendorMark } from "./vendor-mark";

/**
 * Swapping the selected vendor: the comp fades the rail body out, exchanges
 * the record at 120ms, and fades the new one back over 220ms.
 */
const railSwap: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { duration: 0.22, ease: easeOutSoft } },
  exit: { opacity: 0, transition: { duration: 0.12, ease: easeOutSoft } },
};

const MIN_WIDTH = 320;
const MAX_WIDTH = 620;
const OPEN_WIDTH = 390;
const MINI_WIDTH = 56;

/**
 * The persistent vendor rail. It collapses to a 56px spine and can be dragged
 * wider between 320 and 620px, both of which the comp does by hand on the
 * element's inline size.
 */
export function VendorRail({ vendor }: { vendor: Vendor }) {
  const [open, setOpen] = useState(true);
  const [width, setWidth] = useState(OPEN_WIDTH);
  const [dragging, setDragging] = useState(false);
  const endDragRef = useRef<(() => void) | null>(null);
  const reduced = useReducedMotion();

  // A drag that is still live when the screen unmounts would leave listeners
  // and a col-resize cursor behind on the document.
  useEffect(() => () => endDragRef.current?.(), []);

  const startResize = useCallback((event: React.MouseEvent<HTMLDivElement>) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = width;

    const move = (moveEvent: MouseEvent) => {
      setWidth(
        Math.max(
          MIN_WIDTH,
          Math.min(MAX_WIDTH, startWidth - (moveEvent.clientX - startX)),
        ),
      );
    };
    const up = () => {
      document.removeEventListener("mousemove", move);
      document.removeEventListener("mouseup", up);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      endDragRef.current = null;
      setDragging(false);
    };

    document.addEventListener("mousemove", move);
    document.addEventListener("mouseup", up);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    endDragRef.current = up;
    setDragging(true);
  }, [width]);

  const toggle = useCallback(() => setOpen((prev) => !prev), []);

  return (
    <motion.aside
      initial={false}
      animate={{ width: open ? width : MINI_WIDTH }}
      transition={dragging || reduced ? { duration: 0 } : transitions.slow}
      className="relative flex-none border-l border-line bg-paper"
    >
      {open && (
        <div
          onMouseDown={startResize}
          title="Drag to resize"
          className={cn(
            "absolute top-0 bottom-0 -left-1 z-[6] w-[9px] cursor-col-resize transition-colors duration-[180ms] ease-[var(--ease-out-soft)] hover:bg-[rgba(46,128,71,0.16)]",
            dragging && "bg-[rgba(46,128,71,0.22)]",
          )}
        />
      )}

      <div className="relative h-full overflow-hidden">
        <AnimatePresence initial={false}>
          {open ? (
            <motion.div
              key="full"
              variants={crossFade}
              initial="hidden"
              animate="visible"
              exit="exit"
              style={{ width }}
              className="absolute inset-y-0 right-0 bg-paper"
            >
              <div className="h-full overflow-y-auto px-6 pt-[26px] pb-[34px]">
                <AnimatePresence mode="wait" initial={false}>
                  <motion.div
                    key={vendor.id}
                    variants={railSwap}
                    initial="hidden"
                    animate="visible"
                    exit="exit"
                  >
                    <VendorDetail vendor={vendor} onCollapse={toggle} />
                  </motion.div>
                </AnimatePresence>
              </div>
            </motion.div>
          ) : (
            <motion.div
              key="mini"
              variants={crossFade}
              initial="hidden"
              animate="visible"
              exit="exit"
              className="absolute inset-y-0 right-0 flex w-14 flex-col items-center gap-[18px] bg-panel-hover py-[22px]"
            >
              <button
                type="button"
                onClick={toggle}
                title="Expand vendor detail"
                aria-label="Expand vendor detail"
                className="flex h-[30px] w-[30px] cursor-pointer items-center justify-center rounded-lg border border-transparent text-muted-3 transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-wash-deep"
              >
                <CaretLeftIcon size={13} />
              </button>
              <VendorMark vendor={vendor} variant="mini" />
              <div className="text-eyebrow font-medium tracking-[0.14em] whitespace-nowrap text-faint [writing-mode:vertical-rl] rotate-180">
                VENDOR DETAIL
              </div>
              <div className="font-display text-md whitespace-nowrap text-ink-deep [writing-mode:vertical-rl] rotate-180">
                {vendor.name}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.aside>
  );
}
