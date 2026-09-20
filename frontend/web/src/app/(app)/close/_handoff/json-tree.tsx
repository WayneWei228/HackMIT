"use client";

import { useState } from "react";

/**
 * A JSON value, printed as JSON and foldable at every object and array.
 *
 * It prints what it is given and nothing else: no key is renamed, dropped or
 * reordered, so what is on screen is what is in the file.
 */
export function JsonTree({
  value,
  marks = NO_MARKS,
}: {
  value: unknown;
  /** Numbers to mark wherever they appear - the case's own arithmetic. */
  marks?: ReadonlySet<number>;
}) {
  return (
    <pre className="m-0 overflow-x-auto font-mono text-micro leading-[1.65] whitespace-pre text-ink-2">
      <Node value={value} depth={0} last marks={marks} />
    </pre>
  );
}

const NO_MARKS: ReadonlySet<number> = new Set();

/** How many marked numbers sit inside - a branch holding any starts open. */
export function countMarks(value: unknown, marks: ReadonlySet<number>): number {
  if (marks.size === 0) return 0;
  if (typeof value === "number") return marks.has(value) ? 1 : 0;
  if (value === null || typeof value !== "object") return 0;
  return Object.values(value).reduce<number>(
    (sum, item) => sum + countMarks(item, marks),
    0,
  );
}

/** Deeper than this starts folded - a row's own fields show, their innards wait. */
const OPEN_DEPTH = 2;

function Node({
  value,
  depth,
  last,
  name,
  marks,
}: {
  value: unknown;
  depth: number;
  last: boolean;
  name?: string;
  marks: ReadonlySet<number>;
}) {
  const [open, setOpen] = useState(
    () => depth < OPEN_DEPTH || countMarks(value, marks) > 0,
  );
  const pad = "  ".repeat(depth);
  const comma = last ? "" : ",";
  const label =
    name === undefined ? null : (
      <>
        <span className="text-accent-dark">{JSON.stringify(name)}</span>
        {": "}
      </>
    );

  if (value === null || typeof value !== "object") {
    return (
      <>
        {pad}
        {label}
        <Scalar value={value} marked={typeof value === "number" && marks.has(value)} />
        {comma}
        {"\n"}
      </>
    );
  }

  const isArray = Array.isArray(value);
  const entries: [string | undefined, unknown][] = isArray
    ? (value as unknown[]).map((item) => [undefined, item])
    : Object.entries(value as Record<string, unknown>);
  const [opener, closer] = isArray ? ["[", "]"] : ["{", "}"];

  if (entries.length === 0) {
    return (
      <>
        {pad}
        {label}
        {opener}
        {closer}
        {comma}
        {"\n"}
      </>
    );
  }

  const count = `${entries.length} ${isArray ? "item" : "key"}${entries.length === 1 ? "" : "s"}`;

  return (
    <>
      {pad}
      {label}
      <button
        type="button"
        onClick={() => setOpen((was) => !was)}
        aria-expanded={open}
        title={open ? "Fold" : "Unfold"}
        className="cursor-pointer rounded-[3px] border-0 bg-transparent p-0 font-mono text-inherit hover:bg-wash"
      >
        {opener}
        {!open && (
          <>
            <span className="px-1 text-faint-2">{count}</span>
            {closer}
          </>
        )}
      </button>
      {!open && comma}
      {"\n"}
      {open && (
        <>
          {entries.map(([key, item], index) => (
            <Node
              key={key ?? index}
              name={key}
              value={item}
              depth={depth + 1}
              marks={marks}
              last={index === entries.length - 1}
            />
          ))}
          {pad}
          {closer}
          {comma}
          {"\n"}
        </>
      )}
    </>
  );
}

function Scalar({ value, marked }: { value: unknown; marked: boolean }) {
  if (marked) {
    return (
      <mark className="rounded-[3px] bg-accent-soft-2 px-[3px] font-semibold text-accent-dark">
        {String(value)}
      </mark>
    );
  }
  if (typeof value === "string") {
    return <span className="text-ink-3">{JSON.stringify(value)}</span>;
  }
  if (value === null) return <span className="text-ghost">null</span>;
  return <span className="text-accent">{String(value)}</span>;
}
