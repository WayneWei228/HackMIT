"use client";

import Link from "next/link";
import { motion } from "motion/react";
import { useState } from "react";

import { API_BASE_URL } from "@/lib/api";
import { riseIn, staggerParent } from "@/lib/motion";
import { agentChain, withCase } from "@/lib/routes";

import { usd } from "../../_handoff/format";
import type {
  Recheck,
  StoryDocument,
  StoryStep,
  VendorStory,
} from "../../_handoff/types";
import { Letter, letterFromText } from "./letter";
import {
  dayLabel,
  daysBetween,
  tell,
  tokenLabel,
  type Telling,
} from "./story-copy";
import { storyHref } from "./story-href";

type Told = { step: StoryStep; told: Telling };

/** One step, or a run of a close's routine steps read as a single line. */
type Item =
  | { kind: "step"; entry: Told }
  | { kind: "routine"; entries: Told[] };

/** The steps of one case inside one day. `named` when the telling has just moved to this case. */
type CaseBlock = { caseId: string; title: string; named: boolean; items: Item[] };
type Day = { day: string; blocks: CaseBlock[] };

/**
 * Days, then the cases inside a day, then that case's steps - with a close's
 * routine (owed, looked up, classified, booked) folded into one line wherever
 * two or more of its quiet steps follow one another. The API's order is never
 * touched: `day` already runs forward only.
 */
function arrange(story: VendorStory): Day[] {
  const days: Day[] = [];
  let lastCase: string | null = null;
  /* Cases the cutoff has already booked: a document for one of them is late. */
  const closed = new Set<string>();

  story.steps.forEach((step) => {
    const entry: Told = {
      step,
      told: tell(step, closed.has(step.case_id), story.vendor_name),
    };
    if (step.facts.kind === "close") closed.add(step.case_id);

    let day = days[days.length - 1];
    if (!day || day.day !== step.day) {
      day = { day: step.day, blocks: [] };
      days.push(day);
    }
    let block = day.blocks[day.blocks.length - 1];
    if (!block || block.caseId !== step.case_id) {
      block = {
        caseId: step.case_id,
        title: step.case_title,
        named: step.case_id !== lastCase,
        items: [],
      };
      day.blocks.push(block);
    }
    lastCase = step.case_id;

    const open = block.items[block.items.length - 1];
    if (entry.told.quiet && open?.kind === "routine") {
      open.entries.push(entry);
    } else if (entry.told.quiet) {
      block.items.push({ kind: "routine", entries: [entry] });
    } else {
      block.items.push({ kind: "step", entry });
    }
  });

  /* A routine of one is just a step. */
  for (const day of days) {
    for (const block of day.blocks) {
      block.items = block.items.map((item) =>
        item.kind === "routine" && item.entries.length === 1
          ? { kind: "step", entry: item.entries[0] }
          : item,
      );
    }
  }
  return days;
}

/**
 * The vendor, day by day, up to the cut. The date sits in the left margin with
 * how long it had been since the day before; what happened that day hangs off
 * one spine. Where the month ends, the page says so, and how much lies beyond.
 */
export function StoryTimeline({
  story,
  onJson,
}: {
  story: VendorStory;
  onJson: (step: StoryStep) => void;
}) {
  const days = arrange(story);
  const cutDay = dayLabel(story.through_day);

  return (
    <div className="max-w-[1040px]">
      {days.length === 0 && (
        <p className="mt-0 mb-6 max-w-[60ch] text-lead text-muted-3">
          Nothing had happened with {story.vendor_name} by {cutDay}.
        </p>
      )}

      <motion.ol
        variants={staggerParent(0.05)}
        initial="hidden"
        animate="visible"
        className="m-0 list-none p-0"
      >
        {days.map((day, at) => {
          const gap = at > 0 ? daysBetween(days[at - 1].day, day.day) : null;
          return (
            <motion.li
              key={day.day}
              variants={riseIn}
              className="grid grid-cols-[168px_1fr] gap-x-7"
            >
              <div className="pt-[3px] text-right">
                <div className="font-display text-xl leading-[1.2] text-ink-deep">
                  {dayLabel(day.day)}
                </div>
                {gap !== null && gap > 0 && (
                  <div className="mt-1 text-meta text-faint-2">
                    {gap === 1 ? "the next day" : `${gap} days later`}
                  </div>
                )}
              </div>

              <ol className="m-0 list-none border-l border-line-dark p-0 pb-9">
                {day.blocks.map((block) => (
                  <li key={block.caseId} className="m-0 p-0">
                    {block.named && (
                      <div className="pb-2.5 pl-7 text-meta font-medium text-ink-3">
                        {block.title}
                      </div>
                    )}
                    <ol className="m-0 list-none p-0">
                      {block.items.map((item) =>
                        item.kind === "step" ? (
                          <StepRow
                            key={`${item.entry.step.case_id}:${item.entry.step.case_step}`}
                            entry={item.entry}
                            vendorName={story.vendor_name}
                            onJson={onJson}
                          />
                        ) : (
                          <Routine
                            key={`${item.entries[0].step.case_id}:${item.entries[0].step.case_step}`}
                            entries={item.entries}
                            vendorName={story.vendor_name}
                            onJson={onJson}
                          />
                        ),
                      )}
                    </ol>
                  </li>
                ))}
              </ol>
            </motion.li>
          );
        })}
      </motion.ol>

      <TheCut story={story} cutDay={cutDay} />
    </div>
  );
}

/** Where the month ends: what lies beyond it, and the way there. */
function TheCut({ story, cutDay }: { story: VendorStory; cutDay: string }) {
  if (story.later === 0) {
    if (story.steps.length === 0) return null;
    return (
      <div className="grid grid-cols-[168px_1fr] gap-x-7">
        <div />
        <p className="m-0 border-t border-line pt-4 pl-7 text-sm text-faint-2">
          That is everything that has happened with {story.vendor_name} so far.
        </p>
      </div>
    );
  }
  const next = story.months.find((month) => month.month === story.next_month);
  return (
    <div className="grid grid-cols-[168px_1fr] gap-x-7">
      <div className="pt-4 text-right text-meta text-faint-2">{cutDay}</div>
      <div className="border-t border-dashed border-rule pt-4 pl-7">
        <p className="m-0 max-w-[60ch] text-body text-ink-2">
          This is as far as the month knows.{" "}
          {story.later === 1
            ? "One more thing happens"
            : `${story.later} more things happen`}{" "}
          after {cutDay}.
        </p>
        {next && (
          <Link
            href={storyHref(story.vendor_id, next.month)}
            className="mt-2 inline-block rounded-lg border border-line bg-panel px-3 py-1.5 text-meta text-ink transition-colors duration-[160ms] hover:bg-panel-hover"
          >
            Read on through {next.label}
          </Link>
        )}
      </div>
    </div>
  );
}

function agentOfStep(agent: string): { label: string; href: string | null } {
  if (agent === "close") return { label: "Close", href: null };
  const found = agentChain.find((item) => item.id === agent);
  return { label: found?.label ?? agent, href: found?.href ?? null };
}

/** A close's routine, in one line; its steps are one click away. */
function Routine({
  entries,
  vendorName,
  onJson,
}: {
  entries: Told[];
  vendorName: string;
  onJson: (step: StoryStep) => void;
}) {
  const [open, setOpen] = useState(false);

  if (open) {
    return (
      <>
        {entries.map((entry) => (
          <StepRow
            key={`${entry.step.case_id}:${entry.step.case_step}`}
            entry={entry}
            vendorName={vendorName}
            onJson={onJson}
          />
        ))}
        <li className="pb-5 pl-7">
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="cursor-pointer rounded-lg border-0 bg-transparent p-0 pl-[128px] text-meta text-faint-2 transition-colors duration-[160ms] hover:text-ink"
          >
            Fold these {entries.length} steps
          </button>
        </li>
      </>
    );
  }

  const first = agentOfStep(entries[0].step.agent).label;
  const last = agentOfStep(entries[entries.length - 1].step.agent).label;

  return (
    <li className="relative pb-5 pl-7">
      <span
        aria-hidden="true"
        className="absolute top-[7px] -left-[5px] h-[9px] w-[9px] rounded-full border-[1.5px] border-line-dark bg-paper"
      />
      <div className="flex items-baseline gap-4">
        <div className="w-[112px] flex-none text-meta text-faint-2">
          {first} to {last}
        </div>
        <div className="min-w-0 flex-1">
          <p className="m-0 max-w-[72ch] text-body text-ink-2 text-pretty">
            {entries.map((entry) => `${entry.told.headline}.`).join(" ")}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-expanded={false}
          className="flex-none cursor-pointer rounded-lg border-0 bg-transparent px-2 py-1 text-meta text-faint-2 transition-colors duration-[160ms] hover:bg-wash hover:text-ink"
        >
          Show {entries.length} steps
        </button>
      </div>
    </li>
  );
}

function StepRow({
  entry,
  vendorName,
  onJson,
}: {
  entry: Told;
  vendorName: string;
  onJson: (step: StoryStep) => void;
}) {
  const { step, told } = entry;
  const agent = agentOfStep(step.agent);
  /* Told under a later day than its own: the telling never runs backwards. */
  const earlier = step.at !== null && step.at.slice(0, 10) !== step.day;
  const detail = earlier
    ? [told.detail, `already on ${dayLabel(step.at)}`].filter(Boolean).join(", ")
    : told.detail;

  return (
    <li className="group relative pb-5 pl-7">
      {/* The spine's mark: solid where the story turns, hollow for routine. */}
      <span
        aria-hidden="true"
        className={`absolute top-[7px] -left-[5px] h-[9px] w-[9px] rounded-full border-[1.5px] ${
          told.quiet
            ? "border-line-dark bg-paper"
            : "border-accent bg-accent"
        }`}
      />

      <div className="flex items-baseline gap-4">
        <div className="w-[112px] flex-none text-meta text-faint-2">
          {agent.label}
        </div>
        <div className="min-w-0 flex-1">
          <div
            className={
              told.quiet
                ? "text-body text-ink-2"
                : "font-display text-2xl leading-[1.25] text-ink-deep"
            }
          >
            {told.headline}
          </div>
          {detail && (
            <p className="mt-1 mb-0 max-w-[68ch] text-sm leading-[1.5] text-muted-3 text-pretty">
              {detail}
            </p>
          )}
          <StepEvidence step={step} late={!told.quiet} vendorName={vendorName} />
        </div>

        <div className="flex flex-none items-center gap-1 opacity-60 transition-opacity duration-[160ms] group-focus-within:opacity-100 group-hover:opacity-100">
          {agent.href && (
            <Link
              href={withCase(agent.href, step.case_id)}
              className="rounded-lg px-2 py-1 text-meta text-faint-2 transition-colors duration-[160ms] hover:bg-wash hover:text-ink"
            >
              Open {agent.label}
            </Link>
          )}
          <button
            type="button"
            onClick={() => onJson(step)}
            title="The JSON this step read and wrote"
            className="cursor-pointer rounded-lg border-0 bg-transparent px-2 py-1 font-mono text-tiny text-faint-2 transition-colors duration-[160ms] hover:bg-wash hover:text-ink"
          >
            {"{ }"}
          </button>
        </div>
      </div>
    </li>
  );
}

/** What a step can show for itself: the papers, the sum, the letter. */
function StepEvidence({
  step,
  late,
  vendorName,
}: {
  step: StoryStep;
  /** Told as a turn of the story rather than as routine. */
  late: boolean;
  vendorName: string;
}) {
  const facts = step.facts;

  if (facts.kind === "documents") {
    return (
      <div className="mt-2.5 flex flex-col gap-3">
        <div className="flex flex-wrap gap-1.5">
          {facts.documents.map((doc) => (
            <DocumentChip key={doc.doc_id} doc={doc} />
          ))}
        </div>
        {/* A late document is read for a figure; one that came in time is not. */}
        {late &&
          facts.documents
            .filter((doc) => !doc.is_reply && doc.fields.length > 0)
            .map((doc) => <DocumentFields key={doc.doc_id} doc={doc} />)}
        {facts.documents
          .filter((doc) => doc.is_reply && doc.text)
          .map((doc) => (
            <Letter
              key={doc.doc_id}
              direction="received"
              {...letterFromText(doc.text ?? "", vendorName)}
            />
          ))}
      </div>
    );
  }

  if (facts.kind === "estimation" && facts.amount !== null) {
    /* A sum is worth showing; a bare figure only repeats the headline. */
    if (!facts.calculation || !/[-+*/(]/.test(facts.calculation)) return null;
    return (
      <div className="mt-2 font-mono text-micro text-ink-3">
        {facts.calculation} = {usd(facts.amount)}
      </div>
    );
  }

  if (facts.kind === "variance") {
    return (
      <div className="mt-3 flex flex-wrap items-start gap-x-10 gap-y-4">
        {facts.true_up !== null && (
          <div>
            <div className="font-display text-[34px] leading-none text-accent-dark">
              {usd(facts.true_up, true)}
            </div>
            <div className="mt-1.5 text-meta text-faint-2">
              true-up
              {facts.cause ? `, ${tokenLabel(facts.cause).toLowerCase()}` : ""}
            </div>
          </div>
        )}
        {facts.recheck && <RecheckTable recheck={facts.recheck} />}
      </div>
    );
  }

  if (facts.kind === "ask") {
    return (
      <div className="mt-3">
        <Letter
          direction="sent"
          party={[facts.to, facts.asked_of ? tokenLabel(facts.asked_of).toLowerCase() : null]
            .filter(Boolean)
            .join(", ")}
          date={dayLabel(step.at)}
          subject={facts.subject ?? facts.question ?? ""}
          body={facts.body ?? facts.question ?? ""}
          footnote={
            facts.deadline ? `Answer wanted by ${dayLabel(facts.deadline)}` : undefined
          }
        />
      </div>
    );
  }

  return null;
}

function DocumentChip({ doc }: { doc: StoryDocument }) {
  return (
    <a
      href={`${API_BASE_URL}/api/documents/${encodeURIComponent(doc.doc_id)}/file`}
      target="_blank"
      rel="noreferrer"
      title={doc.file_name || doc.doc_id}
      className="flex items-baseline gap-1.5 rounded-md border border-line bg-panel px-2 py-1 transition-colors duration-[160ms] hover:border-line-dark hover:bg-panel-hover"
    >
      <span className="text-meta text-ink">{doc.doc_id}</span>
      {doc.doc_type && (
        <span className="text-tiny text-faint-2">
          {tokenLabel(doc.doc_type).toLowerCase()}
        </span>
      )}
    </a>
  );
}

/** What a late document is read for, most telling first. */
const TELLING_FIELDS = [
  "Amount",
  "Delivered amount",
  "Quantity",
  "Unit rate",
  "Monthly rate",
  "Service period",
  "Coverage start",
  "Coverage end",
  "Effective start",
  "Received date",
];

/** "1400.0" -> "1,400"; anything that is not a plain number is left alone. */
function tidy(value: string): string {
  if (!/^-?\d+(\.\d+)?$/.test(value)) return value;
  const number = Number(value);
  return number.toLocaleString("en-US", {
    maximumFractionDigits: Number.isInteger(number) ? 0 : 6,
  });
}

/** The few fields a late document was read for - the amount, the period, the rate. */
function DocumentFields({ doc }: { doc: StoryDocument }) {
  const seen = new Set<string>();
  const wanted = TELLING_FIELDS.flatMap((label) => {
    const field = doc.fields.find((item) => item.label === label);
    /* An invoice for one unit says its amount three times over; once will do. */
    if (!field || seen.has(field.value)) return [];
    seen.add(field.value);
    return [field];
  }).slice(0, 4);
  if (wanted.length === 0) return null;
  return (
    <dl className="m-0 flex flex-wrap gap-x-7 gap-y-1.5 text-sm">
      {wanted.map((field) => (
        <div key={field.label} className="flex items-baseline gap-2">
          <dt className="text-faint-2">{field.label}</dt>
          <dd className="m-0 text-ink-2 tabular-nums">{tidy(field.value)}</dd>
        </div>
      ))}
    </dl>
  );
}

/** What settlement went back to before deciding whose change this was. */
function RecheckTable({ recheck }: { recheck: Recheck }) {
  const rows: { label: string; value: string }[] = [];
  if (recheck.contract_rate_at_close !== null) {
    rows.push({
      label: "Contract rate at the close",
      value: usd(recheck.contract_rate_at_close),
    });
  }
  if (recheck.po_rate !== null) {
    rows.push({ label: "Purchase order rate", value: usd(recheck.po_rate) });
  }
  if (recheck.prior_invoice_amounts.length > 0) {
    rows.push({
      label: "Earlier invoices",
      value: recheck.prior_invoice_amounts.map((amount) => usd(amount)).join(", "),
    });
  }
  if (rows.length === 0 && recheck.notes.length === 0) return null;

  return (
    <div className="min-w-[300px] flex-1">
      <div className="text-meta text-faint-2">
        It went back to what the close knew
      </div>
      <dl className="mt-1.5 mb-0 border-t border-line">
        {rows.map((row) => (
          <div
            key={row.label}
            className="flex items-baseline justify-between gap-6 border-b border-line py-1.5 text-sm"
          >
            <dt className="text-muted-3">{row.label}</dt>
            <dd className="m-0 text-ink tabular-nums">{row.value}</dd>
          </div>
        ))}
      </dl>
      {recheck.consistent_at_close !== null && (
        <p className="mt-2 mb-0 text-sm text-ink-2">
          {recheck.consistent_at_close
            ? "All of it agreed with the accrual: what the close knew was right."
            : "They did not agree with each other at the close."}
        </p>
      )}
      {recheck.notes.map((note) => (
        <p key={note} className="mt-1 mb-0 text-sm text-muted-3">
          {note}
        </p>
      ))}
    </div>
  );
}
