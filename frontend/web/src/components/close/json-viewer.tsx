"use client";

import { useState } from "react";

import { cn } from "@/lib/cn";

/** Strings longer than this are cut with a "show all" until the reader opens them. */
const LONG_STRING = 96;
/** Arrays and objects longer than this show their first entries and a "show all". */
const LONG_LIST = 12;

type Json = unknown;

function isRecord(value: Json): value is Record<string, Json> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function Primitive({ value }: { value: Json }) {
  const [open, setOpen] = useState(false);
  if (value === null) return <span className="text-ghost">null</span>;
  if (typeof value === "boolean") return <span className="text-[#8A6516]">{String(value)}</span>;
  if (typeof value === "number") return <span className="text-[#3F5A7C]">{value}</span>;
  const text = String(value);
  const long = text.length > LONG_STRING;
  const shown = long && !open ? `${text.slice(0, LONG_STRING)}...` : text;
  return (
    <span className="break-words text-accent-deep">
      &quot;{shown}&quot;
      {long && (
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="ml-1.5 cursor-pointer rounded-sm bg-wash px-1 text-nano font-sans font-medium text-muted-4 hover:text-ink"
        >
          {open ? "show less" : "show all"}
        </button>
      )}
    </span>
  );
}

function Caret({ open }: { open: boolean }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "inline-block w-3 flex-none text-[9px] text-ghost transition-transform duration-[160ms]",
        open && "rotate-90",
      )}
    >
      {"▸"}
    </span>
  );
}

function Node({ name, value, depth }: { name?: string; value: Json; depth: number }) {
  const container = Array.isArray(value) || isRecord(value);
  const [open, setOpen] = useState(depth < 1);
  const [all, setAll] = useState(false);

  const key = name !== undefined && <span className="text-ink-2">&quot;{name}&quot;: </span>;
  if (!container) {
    return (
      <div className="pl-3">
        {key}
        <Primitive value={value} />
      </div>
    );
  }

  const entries: [string, Json][] = Array.isArray(value)
    ? value.map((item, index) => [String(index), item])
    : Object.entries(value as Record<string, Json>);
  const isArray = Array.isArray(value);
  const brackets = isArray ? ["[", "]"] : ["{", "}"];
  const shown = all ? entries : entries.slice(0, LONG_LIST);

  return (
    <div className={depth === 0 ? undefined : "pl-3"}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full cursor-pointer items-baseline text-left hover:text-ink"
      >
        <Caret open={open} />
        {key}
        <span className="text-muted-4">
          {brackets[0]}
          {!open && (
            <span className="text-ghost">
              {" "}
              {entries.length} {isArray ? "items" : "keys"}{" "}
            </span>
          )}
          {!open && brackets[1]}
        </span>
      </button>
      {open && (
        <>
          {shown.map(([childKey, child]) => (
            <Node
              key={childKey}
              name={isArray ? undefined : childKey}
              value={child}
              depth={depth + 1}
            />
          ))}
          {entries.length > LONG_LIST && (
            <div className="pl-6">
              <button
                type="button"
                onClick={() => setAll((v) => !v)}
                className="cursor-pointer rounded-sm bg-wash px-1.5 py-0.5 text-nano font-sans font-medium text-muted-4 hover:text-ink"
              >
                {all ? "show fewer" : `show all ${entries.length}`}
              </button>
            </div>
          )}
          <div className="pl-3 text-muted-4">{brackets[1]}</div>
        </>
      )}
    </div>
  );
}

/**
 * A small collapsible JSON viewer. Values are shown exactly as the backend sent
 * them - money stays a Decimal string - and nothing here parses or reformats a
 * number.
 */
export function JsonViewer({
  value,
  className,
  maxHeight = 260,
}: {
  value: unknown;
  className?: string;
  maxHeight?: number;
}) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(JSON.stringify(value, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div
      className={cn(
        "relative rounded-lg border border-line bg-[#F7F7F2] font-mono text-tiny leading-[1.65] text-ink-3",
        className,
      )}
    >
      <button
        type="button"
        onClick={copy}
        aria-label="Copy JSON"
        className="absolute top-1.5 right-1.5 z-[1] cursor-pointer rounded-md border border-line bg-panel px-2 py-[3px] font-sans text-nano font-medium text-muted-4 transition-colors duration-[160ms] hover:text-ink"
      >
        {copied ? "Copied" : "Copy"}
      </button>
      <div style={{ maxHeight }} className="overflow-auto px-3 py-2.5 pr-14">
        <Node value={value} depth={0} />
      </div>
    </div>
  );
}
