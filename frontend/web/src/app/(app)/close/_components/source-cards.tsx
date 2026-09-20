import { Fragment } from "react";

import { cn } from "@/lib/cn";
import type { Preview } from "@/lib/api-types";

/**
 * The document previews.
 *
 * Each card is a miniature of the real artifact rather than a generic tile.
 * The backend describes a file's preview with one of seven layouts (`card`),
 * and the bodies share only a handful of primitives - a serif title, a
 * hairline rule, a label/value grid and the grey bars that stand in for body
 * copy.
 */

/* -------------------------------------------------------------------------- */
/* Shared card pieces                                                          */
/* -------------------------------------------------------------------------- */

function CardTitle({
  children,
  size = "lg",
}: {
  children: React.ReactNode;
  size?: "lg" | "md";
}) {
  return (
    <div
      className={cn(
        "font-display leading-[1.1] text-ink-deep",
        size === "lg" ? "text-xl" : "text-lg",
      )}
    >
      {children}
    </div>
  );
}

function CardKicker({ children }: { children: React.ReactNode }) {
  return <div className="mt-[5px] text-pico text-muted-6">{children}</div>;
}

function CardRule({ className }: { className?: string }) {
  return <div className={cn("h-px bg-[#EAEAE3]", className)} />;
}

/** The grey bars that stand in for unrendered body copy. */
function BodyBar({ className }: { className?: string }) {
  return <div className={cn("h-[5px] rounded-xs bg-wash-cool", className)} />;
}

/** A small table: header row, then rows. The last column reads as a figure. */
function PreviewTable({
  columns,
  rows,
}: {
  columns: readonly string[];
  rows: readonly (readonly string[])[];
}) {
  const dated = columns[0] === "DATE";
  const template = dated
    ? "52px minmax(0,1fr) auto"
    : `repeat(${columns.length - 1}, minmax(0,1fr)) auto`;
  return (
    <>
      <div
        style={{ gridTemplateColumns: template }}
        className="mt-3.5 grid gap-x-1.5 border-b border-[#EAEAE3] pb-[5px] text-[7.5px] tracking-[0.08em] text-ghost"
      >
        {columns.map((column, i) => (
          <div key={column} className={i === columns.length - 1 ? "text-right" : undefined}>
            {column}
          </div>
        ))}
      </div>
      <div
        style={{ gridTemplateColumns: template }}
        className="mt-2 grid gap-x-1.5 gap-y-2 text-nano text-ink-3 tabular-nums"
      >
        {rows.map((row, r) => (
          <Fragment key={`${r}-${row.join("|")}`}>
            {row.map((cell, i) => (
              <div key={`${r}-${i}`} className={i === row.length - 1 ? "text-right" : undefined}>
                {cell}
              </div>
            ))}
          </Fragment>
        ))}
      </div>
    </>
  );
}

function FieldGrid({ fields }: { fields: readonly (readonly [string, string])[] }) {
  return (
    <div className="mt-4 grid grid-cols-[1fr_auto] gap-x-2 gap-y-2.5 text-nano text-ink-3">
      {fields.map(([label, value]) => (
        <Fragment key={label}>
          <div className="text-ghost">{label}</div>
          <div className="text-right">{value}</div>
        </Fragment>
      ))}
    </div>
  );
}

/** Memo and email headers: a narrow label column and the value beside it. */
function HeaderFields({
  fields,
  labelWidth,
  small = false,
}: {
  fields: Record<string, string>;
  labelWidth: string;
  small?: boolean;
}) {
  return (
    <div
      style={{ gridTemplateColumns: `${labelWidth} 1fr` }}
      className={cn(
        "mt-3.5 grid gap-1.5 text-ink-3",
        small ? "text-[8px]" : "text-nano",
      )}
    >
      {Object.entries(fields).map(([label, value]) => (
        <Fragment key={label}>
          <div className="text-ghost">{label}</div>
          <div className="min-w-0 break-words">{value}</div>
        </Fragment>
      ))}
    </div>
  );
}

function Lines({ text }: { text: string }) {
  return (
    <>
      {text.split("\n").map((line, i) => (
        <Fragment key={`${i}-${line}`}>
          {i > 0 && <br />}
          {line}
        </Fragment>
      ))}
    </>
  );
}

/* -------------------------------------------------------------------------- */
/* Card bodies                                                                 */
/* -------------------------------------------------------------------------- */

export function PreviewBody({ preview }: { preview: Preview }) {
  switch (preview.card) {
    case "clause":
      return (
        <>
          <CardTitle>{preview.title}</CardTitle>
          <CardKicker>{preview.subtitle}</CardKicker>
          <CardRule className="my-[11px]" />
          <div className="text-pico font-semibold text-[#2D302A]">
            {preview.heading}
          </div>
          <div className="mt-[9px] flex gap-[7px]">
            <div className="flex-none text-nano text-ghost tabular-nums">
              {preview.clause_no}
            </div>
            <div className="text-nano leading-[1.7] text-pretty text-ink-3">
              {preview.text}
            </div>
          </div>
        </>
      );
    case "table":
      return (
        <>
          <CardTitle>{preview.title}</CardTitle>
          <CardKicker>{preview.subtitle}</CardKicker>
          <PreviewTable columns={preview.columns} rows={preview.rows} />
        </>
      );
    case "record":
      return (
        <>
          <CardTitle>{preview.title}</CardTitle>
          <div className="mt-1.5 text-[8px] tracking-caps text-ghost">
            {preview.subtitle.toUpperCase()}
          </div>
          <div className="mt-3.5 grid grid-cols-[auto_1fr] gap-x-2 gap-y-[9px] text-nano text-ink-3">
            {preview.fields.map(([label, value]) => (
              <Fragment key={label}>
                <div className="text-ghost">{label}</div>
                <div className="text-right leading-[1.5]">{value}</div>
              </Fragment>
            ))}
          </div>
        </>
      );
    case "memo":
      return (
        <>
          <CardTitle>{preview.title}</CardTitle>
          <CardKicker>{preview.subtitle}</CardKicker>
          <HeaderFields fields={preview.fields} labelWidth="38px" />
          <div className="mt-3 text-nano leading-[1.75] text-pretty text-ink-3">
            {preview.body}
          </div>
        </>
      );
    case "email":
      return (
        <>
          <CardTitle size="md">{preview.title}</CardTitle>
          <HeaderFields fields={preview.fields} labelWidth="34px" small />
          <div className="mt-3.5 text-nano leading-[1.75] text-pretty text-ink-3">
            <Lines text={preview.body} />
          </div>
        </>
      );
    case "chat":
      return (
        <>
          <CardTitle size="md">{preview.title}</CardTitle>
          <CardKicker>{preview.subtitle}</CardKicker>
          <div className="mt-[15px] flex flex-col gap-[11px]">
            {preview.messages.map((message) => (
              <div key={`${message.sender}-${message.time}-${message.text}`}>
                <div className="flex items-baseline gap-[7px]">
                  <span className="text-nano font-semibold text-[#2D302A]">
                    {message.sender}
                  </span>
                  <span className="text-[8px] text-ghost tabular-nums">
                    {message.time}
                  </span>
                </div>
                <div className="mt-[3px] text-nano leading-[1.7] text-ink-3">
                  {message.text}
                </div>
              </div>
            ))}
          </div>
        </>
      );
    case "skeleton":
      return (
        <>
          <CardTitle size="md">{preview.title}</CardTitle>
          <CardKicker>{preview.subtitle}</CardKicker>
          <FieldGrid fields={preview.fields} />
          {preview.total && (
            <>
              <CardRule className="mt-3.5 mb-3" />
              <div className="flex items-baseline justify-between text-pico font-semibold text-ink">
                <div>{preview.total[0]}</div>
                <div className="tabular-nums">{preview.total[1]}</div>
              </div>
            </>
          )}
          <BodyBar className={preview.total ? "mt-[22px]" : "mt-[26px]"} />
          <BodyBar className="mt-[7px] w-[68%]" />
        </>
      );
  }
}
