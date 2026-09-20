"use client";

import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "motion/react";

import { ChevronDownIcon, ChevronRightIcon } from "@/components/ui/icons";
import { SectionLabel } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import { easeOutSoft, transitions } from "@/lib/motion";
import { documentTypeLabel } from "@/lib/use-case-documents";

import {
  SELECTION_STEP,
  asList,
  type DocId,
  type SelectionFile,
} from "../_data";
import { useEvidenceData } from "./data-context";

/** What a file is called on screen: its own name, or its id when it has none. */
const nameOf = (file: SelectionFile) => file.fileName || file.docId;

/** Why a file was passed over, in as many words as the backend gave us. */
const passedOver = (file: SelectionFile) =>
  file.belongsTo ? `Other line · ${file.belongsTo}` : "Not this case's";

/**
 * One mark per file the agent read. They all start the same; once the agent
 * has collected the case's documents the kept ones take the accent and the
 * rest fall back, so the narrowing is visible before a word is read.
 */
function Marks({
  files,
  narrowed,
}: {
  files: readonly SelectionFile[];
  narrowed: boolean;
}) {
  return (
    <div
      aria-hidden
      className="flex min-w-0 flex-1 items-center gap-[3px] overflow-hidden"
    >
      {files.map((file, i) => (
        <span
          key={`${file.docId}-${i}`}
          title={nameOf(file)}
          className={cn(
            "h-[14px] w-[5px] flex-none rounded-[2px] transition-[background-color,opacity] duration-[420ms] ease-[var(--ease-out-soft)]",
            !narrowed && "bg-ghost",
            narrowed && file.selected && "bg-accent",
            narrowed && !file.selected && "bg-line-deep opacity-50",
          )}
          style={{ transitionDelay: narrowed ? `${i * 18}ms` : undefined }}
        />
      ))}
    </div>
  );
}

/** One file in the opened list. A kept file opens in the reader below. */
function FileRow({
  file,
  narrowed,
  active,
  onSelect,
}: {
  file: SelectionFile;
  narrowed: boolean;
  active: boolean;
  onSelect: (id: DocId) => void;
}) {
  const kept = narrowed && file.selected;
  const type = documentTypeLabel(file.docType);
  const body = (
    <>
      <span
        className={cn(
          "h-[14px] w-[5px] flex-none rounded-[2px]",
          kept ? "bg-accent" : "bg-line-deep",
        )}
      />
      <span className="min-w-0 flex-1">
        <span
          className={cn(
            "block truncate text-sm leading-tight",
            kept ? "text-ink" : "text-muted",
          )}
        >
          {nameOf(file)}
        </span>
        <span className="mt-[3px] block truncate text-micro text-ghost">
          {file.period ? `${type} · ${file.period}` : type}
        </span>
      </span>
      {narrowed && (
        <span
          className={cn(
            "flex-none text-micro whitespace-nowrap",
            kept ? "text-accent" : "text-ghost",
          )}
        >
          {file.selected ? (file.reason ?? "Kept") : passedOver(file)}
        </span>
      )}
    </>
  );

  const shape =
    "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-[7px] text-left transition-colors duration-[160ms] ease-[var(--ease-out-soft)]";

  if (!kept) {
    return (
      <div className={cn(shape, narrowed && "opacity-60")}>{body}</div>
    );
  }
  return (
    <button
      type="button"
      onClick={() => onSelect(file.docId)}
      aria-pressed={active}
      className={cn(shape, "cursor-pointer", active ? "bg-wash" : "hover:bg-wash")}
    >
      {body}
    </button>
  );
}

/**
 * The file selection strip: every file the agent read, narrowed to the ones
 * this case was decided on.
 *
 * The tab strip under it only ever shows the kept files, which hides the
 * choosing. This says how many there were to choose from, shows the cut as it
 * happens in the run, and opens into the whole list with the reason each kept
 * file was kept. Every count, name and reason is the backend's; with no
 * selection in the payload the strip is simply not drawn.
 */
export function FileSelection({
  step,
  doc,
  onSelect,
}: {
  step: number;
  doc: DocId;
  onSelect: (id: DocId) => void;
}) {
  const selection = useEvidenceData().data.SELECTION;
  const [open, setOpen] = useState(false);

  /* Kept files first, each group in the order the agent read them. */
  const files = useMemo(() => {
    const all = asList(selection?.files).filter((file) => file && file.docId);
    return [...all.filter((f) => f.selected), ...all.filter((f) => !f.selected)];
  }, [selection]);

  if (!selection || files.length === 0) return null;

  const narrowed = step >= SELECTION_STEP;
  const { total, selected } = selection;

  return (
    <div className="pb-[14px]">
      <div className="flex items-center gap-4">
        <SectionLabel className="flex-none text-[10.5px] text-faint">
          File selection
        </SectionLabel>

        <div className="flex flex-none items-center gap-2 text-sm leading-none whitespace-nowrap">
          <span className="text-muted">
            <span className="font-medium text-ink">{total}</span>{" "}
            {total === 1 ? "file" : "files"} read
          </span>
          <ChevronRightIcon size={10} className="text-faint-2" />
          <span className="relative inline-block min-w-[150px]">
            <AnimatePresence initial={false} mode="wait">
              {narrowed ? (
                <motion.span
                  key="kept"
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3, ease: easeOutSoft }}
                  className="inline-block text-muted"
                >
                  <span className="font-medium text-accent">{selected}</span>{" "}
                  relevant to this case
                </motion.span>
              ) : (
                <motion.span
                  key="choosing"
                  exit={{ opacity: 0, transition: transitions.fast }}
                  className="inline-block text-ghost"
                >
                  choosing...
                </motion.span>
              )}
            </AnimatePresence>
          </span>
        </div>

        <Marks files={files} narrowed={narrowed} />

        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          className="flex flex-none cursor-pointer items-center gap-[7px] rounded-xl px-2.5 py-2 text-sm leading-none whitespace-nowrap text-muted transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-wash"
        >
          {open ? "Hide files" : "All files"}
          <ChevronDownIcon
            size={11}
            className={cn(
              "text-faint-2 transition-transform duration-[160ms]",
              open && "rotate-180",
            )}
          />
        </button>
      </div>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            key="files"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={transitions.base}
            className="overflow-hidden"
          >
            <div className="mt-2.5 grid max-h-[176px] grid-cols-2 gap-x-4 gap-y-px overflow-y-auto rounded-xl border border-line-soft bg-panel p-1.5">
              {files.map((file, i) => (
                <FileRow
                  key={`${file.docId}-${i}`}
                  file={file}
                  narrowed={narrowed}
                  active={file.docId === doc}
                  onSelect={onSelect}
                />
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
