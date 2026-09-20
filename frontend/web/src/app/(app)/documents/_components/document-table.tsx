"use client";

import { motion, useReducedMotion } from "motion/react";

import { cn } from "@/lib/cn";
import { staggerParent } from "@/lib/motion";

import { DOCUMENT_GRID } from "./document-grid";
import { DocumentRow } from "./document-row";
import { COLUMNS, type DocumentEntry } from "../_data";

/**
 * The documents a close read, in the order the API lists them.
 *
 * The columns do not sort: this is the intake record for a month, and the
 * order it arrived in is part of what it says.
 */
export function DocumentTable({ docs }: { docs: readonly DocumentEntry[] }) {
  const reduced = useReducedMotion();

  return (
    <>
      <div className={cn(DOCUMENT_GRID, "border-b border-line px-2.5 pb-[11px]")}>
        {COLUMNS.map((label) => (
          <div
            key={label}
            className="text-eyebrow font-medium tracking-[0.12em] whitespace-nowrap text-faint"
          >
            {label}
          </div>
        ))}
      </div>

      <motion.div
        variants={staggerParent(0.045)}
        initial={reduced ? false : "hidden"}
        animate="visible"
      >
        {docs.map((doc) => (
          <DocumentRow key={doc.doc_id} doc={doc} />
        ))}
      </motion.div>
    </>
  );
}
