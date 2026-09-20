"use client";

import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";

import { handoffPath } from "@/lib/api";
import { agentChain } from "@/lib/routes";
import { useLiveData } from "@/lib/use-live-data";

import { usd } from "./format";
import { countMarks, JsonTree } from "./json-tree";
import type {
  HandoffChain,
  HandoffPart,
  HandoffStep,
  PeriodCase,
  Situation,
} from "./types";

type Side = "input" | "output";

/**
 * The `{ } JSON` button in an agent's status bar, and the drawer it opens.
 *
 * The drawer is the case's whole chain as it is on disk, in the order it
 * happened: for every time an agent ran, the JSON it read and the JSON it
 * wrote, each part under the file it lives in. It opens on the agent whose
 * screen this is, and is fetched when it opens, so a screen that never opens
 * it pays nothing.
 */
export function AgentJsonButton({
  agentId,
  caseParam,
}: {
  agentId: string;
  caseParam: string | null;
}) {
  const [open, setOpen] = useState(false);
  if (!caseParam) return null;

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        title="The JSON each agent read and wrote"
        className="flex cursor-pointer items-center gap-[6px] rounded-lg border border-transparent bg-transparent px-[9px] py-1.5 text-meta leading-none whitespace-nowrap text-faint-2 transition-colors duration-[160ms] ease-[var(--ease-out-soft)] hover:bg-wash hover:text-ink"
      >
        <span aria-hidden="true" className="font-mono text-tiny">
          {"{ }"}
        </span>
        JSON
      </button>
      {open && (
        <HandoffDrawer
          agentId={agentId}
          caseParam={caseParam}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}

export function HandoffDrawer({
  agentId,
  caseParam,
  startStep,
  onClose,
}: {
  agentId: string;
  caseParam: string;
  /** Open on this step of the chain rather than on the agent's last run. */
  startStep?: number;
  onClose: () => void;
}) {
  /* The drawer can walk to the period's other cases and to the other agents
     without moving the screen behind it. */
  const [shownCase, setShownCase] = useState(caseParam);
  /* A step is picked by position; until one is, the drawer shows the last run
     of the agent in hand - which is also where it lands on another case. */
  const [agentInHand, setAgentInHand] = useState(agentId);
  const [picked, setPicked] = useState<number | null>(startStep ?? null);
  const [side, setSide] = useState<Side>("output");
  const live = useLiveData<HandoffChain>(handoffPath(shownCase));

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  /* Walking to another case keeps the last one on screen until the next has
     arrived, so the drawer does not blank between them. */
  const [last, setLast] = useState<HandoffChain | null>(null);
  if (live.data && live.data !== last) setLast(live.data);
  const chain = live.status === "loading" ? last : live.data;
  const steps = chain?.steps ?? [];
  const lastRun = steps.findLastIndex((item) => item.agent === agentInHand);
  const shownIndex = picked ?? Math.max(lastRun, 0);
  const step = steps[shownIndex];
  const marks = useMemo(
    () => new Set(chain?.situation.numbers ?? []),
    [chain],
  );

  return createPortal(
    <div className="fixed inset-0 z-50 flex justify-end leading-[normal]">
      <button
        type="button"
        aria-label="Close"
        onClick={onClose}
        className="absolute inset-0 cursor-default border-0 bg-[rgba(29,31,27,0.18)]"
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label="Agent handoff JSON"
        className="relative flex h-full w-[min(980px,96vw)] flex-col border-l border-line bg-paper shadow-[-12px_0_32px_rgba(29,31,27,0.08)]"
      >
        <header className="flex flex-none items-start justify-between gap-4 px-6 pt-5 pb-3.5">
          <div className="min-w-0">
            <div className="text-body font-medium text-ink">
              Agent handoff · JSON
            </div>
            <div className="mt-1 truncate text-meta text-faint-2">
              {chain ? `${chain.vendor_name} · ` : ""}
              {shownCase}
              {chain?.status ? ` · ${chain.status}` : ""}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="cursor-pointer rounded-lg border border-transparent bg-transparent px-[9px] py-1.5 text-meta leading-none text-faint-2 transition-colors duration-[160ms] hover:bg-wash hover:text-ink"
          >
            Close
          </button>
        </header>

        {live.status === "loading" && !chain && (
          <Note>Reading the run directory…</Note>
        )}
        {live.status === "error" && (
          <div className="px-6 text-sm text-ink-2">
            <p className="m-0">The close API could not be reached.</p>
            <p className="mt-1 mb-3 text-meta text-faint-2">
              {live.url} - {live.error}
            </p>
            <button
              type="button"
              onClick={live.retry}
              className="cursor-pointer rounded-lg border border-line bg-panel px-3 py-1.5 text-meta text-ink hover:bg-panel-hover"
            >
              Try again
            </button>
          </div>
        )}
        {live.status === "empty" && (
          <Note>The close API does not know this case.</Note>
        )}

        {chain && (
          <>
            <CaseSwitcher
              cases={chain.cases}
              shown={chain.case_id}
              onPick={(caseId) => {
                setShownCase(caseId);
                setPicked(null);
              }}
            />
            <SituationStrip situation={chain.situation} />

            <div className="flex min-h-0 flex-1 border-t border-line">
              <ChainStepper
                steps={steps}
                marks={marks}
                shown={shownIndex}
                onPick={(index) => {
                  setPicked(index);
                  setAgentInHand(steps[index].agent);
                }}
              />
              <div className="flex min-w-0 flex-1 flex-col">
                {step && (
                  <StepBody
                    /* A new case or step is a new tree: folds start over. */
                    key={`${chain.case_id}:${shownIndex}`}
                    step={step}
                    again={steps.some(
                      (other, index) =>
                        index > shownIndex && other.agent === step.agent,
                    )}
                    side={side}
                    onSide={setSide}
                    marks={marks}
                  />
                )}
              </div>
            </div>
          </>
        )}
      </aside>
    </div>,
    document.body,
  );
}

function Note({ children }: { children: React.ReactNode }) {
  return <p className="m-0 px-6 text-sm text-faint-2">{children}</p>;
}

/** The period's cases - one per situation in a full month - to compare across. */
function CaseSwitcher({
  cases,
  shown,
  onPick,
}: {
  cases: PeriodCase[];
  shown: string;
  onPick: (caseId: string) => void;
}) {
  if (cases.length < 2) return null;
  return (
    <div className="flex flex-none flex-wrap gap-1.5 px-6 pb-3.5">
      {cases.map((item) => {
        const active = item.case_id === shown;
        return (
          <button
            key={item.case_id}
            type="button"
            aria-pressed={active}
            onClick={() => onPick(item.case_id)}
            className={`cursor-pointer rounded-lg border px-2.5 py-1.5 text-left leading-none transition-colors duration-[160ms] ${
              active
                ? "border-accent-line bg-accent-tint"
                : "border-line bg-panel hover:bg-panel-hover"
            }`}
          >
            <span className="text-meta font-medium text-ink">
              {item.vendor_name}
            </span>
            <span className="ml-1.5 text-tiny text-faint-2">
              {item.label ?? item.category ?? "not classified"}
            </span>
          </button>
        );
      })}
    </div>
  );
}

/** The case's arithmetic in one line; every figure is one of the marked numbers. */
function SituationStrip({ situation }: { situation: Situation }) {
  const cells: { label: string; value: string; mono?: boolean }[] = [];
  if (situation.label || situation.category) {
    cells.push({
      label: "Situation",
      value: situation.label ?? situation.category ?? "",
    });
  }
  if (situation.estimator) {
    cells.push({ label: "Estimator", value: situation.estimator, mono: true });
  }
  if (situation.calculation) {
    cells.push({ label: "Calculation", value: situation.calculation, mono: true });
  }
  if (situation.amount !== null) {
    cells.push({ label: "Accrued", value: usd(situation.amount) });
  } else if (situation.missing) {
    cells.push({ label: "Missing", value: situation.missing });
  }
  if (situation.actual !== null) {
    cells.push({ label: "Actual", value: usd(situation.actual) });
  }
  if (situation.true_up !== null) {
    cells.push({
      label: "True-up",
      value: `${usd(situation.true_up, true)}${situation.cause ? ` · ${situation.cause}` : ""}`,
    });
  }
  if (cells.length === 0) return null;

  return (
    <div className="flex-none px-6 pb-4">
      <div className="flex flex-wrap gap-x-7 gap-y-2.5 rounded-[10px] border border-line bg-panel px-4 py-3">
        {cells.map((cell) => (
          <div key={cell.label} className="min-w-0">
            <div className="text-eyebrow tracking-[0.08em] text-faint-2 uppercase">
              {cell.label}
            </div>
            <div
              className={`mt-1 text-ink ${cell.mono ? "font-mono text-micro" : "text-sm font-medium"}`}
            >
              {cell.value}
            </div>
          </div>
        ))}
        {situation.flags.length > 0 && (
          <div className="min-w-0">
            <div className="text-eyebrow tracking-[0.08em] text-faint-2 uppercase">
              Flags
            </div>
            <div className="mt-1 font-mono text-micro text-ink">
              {situation.flags.join(" · ")}
            </div>
          </div>
        )}
      </div>
      {situation.numbers.length > 0 && (
        <p className="mt-2 mb-0 text-tiny text-faint-3">
          <mark className="rounded-[3px] bg-accent-soft-2 px-[3px] font-mono font-semibold text-accent-dark">
            marked
          </mark>{" "}
          values below are these figures, wherever an agent read or wrote them.
        </p>
      )}
    </div>
  );
}

/** `"close"` is the cutoff, not one of the seven agents; the rest are named by the chain. */
function agentLabel(agent: string): string {
  if (agent === "close") return "Close";
  return agentChain.find((item) => item.id === agent)?.label ?? agent;
}

function dayOf(at: string | null): string {
  if (!at) return "";
  const day = new Date(`${at.slice(0, 10)}T00:00:00Z`);
  return day.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  });
}

/** Every run on the case, in the order it happened, under the day it happened. */
function ChainStepper({
  steps,
  marks,
  shown,
  onPick,
}: {
  steps: HandoffStep[];
  marks: ReadonlySet<number>;
  shown: number;
  onPick: (index: number) => void;
}) {
  return (
    <nav
      aria-label="What happened, in order"
      className="w-[264px] flex-none overflow-y-auto border-r border-line bg-rail px-3 pt-1 pb-3"
    >
      {steps.map((step, index) => {
        const active = index === shown;
        const day = dayOf(step.at);
        /* A heading only when time moves forward: a step dated before the one
           that led to it stays under the day already open. */
        const latest = steps
          .slice(0, index)
          .reduce((max, item) => ((item.at ?? "") > max ? (item.at ?? "") : max), "");
        const newDay = index === 0 || (step.at ?? "").slice(0, 10) > latest.slice(0, 10);
        const wroteFigure = countMarks(step.output, marks) > 0;
        return (
          <div key={index}>
            {newDay && day && (
              <div className="px-2.5 pt-3 pb-1 text-eyebrow tracking-[0.08em] text-faint-2 uppercase">
                {day}
              </div>
            )}
            <button
              type="button"
              aria-current={active ? "step" : undefined}
              /* A long chain opens on a late step; bring it into view. */
              ref={
                active
                  ? (node) => node?.scrollIntoView({ block: "nearest" })
                  : undefined
              }
              onClick={() => onPick(index)}
              className={`flex w-full cursor-pointer gap-2.5 rounded-lg border px-2.5 py-[7px] text-left transition-colors duration-[160ms] ${
                active
                  ? "border-line bg-panel"
                  : "border-transparent bg-transparent hover:bg-hover"
              }`}
            >
              <span
                className={`pt-px font-mono text-tiny tabular-nums ${active ? "text-accent" : "text-faint-3"}`}
              >
                {String(index + 1).padStart(2, "0")}
              </span>
              <span className="min-w-0 flex-1">
                <span
                  className={`block text-sm ${active ? "font-medium text-ink" : "text-ink-3"}`}
                >
                  {agentLabel(step.agent)}
                  {wroteFigure && (
                    <span
                      title="Wrote one of the marked figures"
                      className="ml-1.5 inline-block h-[5px] w-[5px] rounded-full bg-accent align-middle"
                    />
                  )}
                </span>
                <span
                  title={step.result}
                  className="mt-0.5 line-clamp-2 text-tiny text-muted-3"
                >
                  {step.result}
                </span>
              </span>
            </button>
          </div>
        );
      })}
    </nav>
  );
}

function StepBody({
  step,
  again,
  side,
  onSide,
  marks,
}: {
  step: HandoffStep;
  /** The same agent runs again later on this case. */
  again: boolean;
  side: Side;
  onSide: (side: Side) => void;
  marks: ReadonlySet<number>;
}) {
  const label = agentLabel(step.agent);
  const tabs: { side: Side; title: string; hint: string }[] = [
    { side: "input", title: "Read", hint: "what there was at that moment" },
    { side: "output", title: "Wrote", hint: "what the next step picks up" },
  ];
  /* The blocks that carry the case's figures come first; the rest keep the
     order the API gave them. */
  const parts = step[side]
    .map((part) => ({ part, count: countMarks(part.data, marks) }))
    .sort((a, b) => Number(b.count > 0) - Number(a.count > 0));

  return (
    <>
      <div role="tablist" className="flex flex-none gap-1 border-b border-line px-5 pt-2">
        {tabs.map((tab) => {
          const active = tab.side === side;
          return (
            <button
              key={tab.side}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => onSide(tab.side)}
              className={`-mb-px cursor-pointer border-0 border-b-2 bg-transparent px-3 pt-1 pb-2.5 text-left transition-colors duration-[160ms] ${
                active
                  ? "border-accent text-ink"
                  : "border-transparent text-faint-2 hover:text-ink"
              }`}
            >
              <span className="text-sm font-medium">
                {tab.title}
                <span className="ml-1.5 font-normal text-faint-2 tabular-nums">
                  {step[tab.side].length}
                </span>
              </span>
              <span className="block pt-0.5 text-tiny text-faint-3">
                {tab.hint}
              </span>
            </button>
          );
        })}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
        <p className="mt-0 mb-3.5 text-sm text-ink-2">{step.result}</p>
        {again && side === "output" && (
          <p className="mt-0 mb-3.5 text-tiny text-faint-3">
            {label} runs again later on this case. What it wrote is shown as it
            stands on disk now, after that later run; a decision_log, where
            there is one, is this run alone.
          </p>
        )}
        {parts.length === 0 ? (
          <p className="m-0 text-sm text-faint-2">
            {side === "output"
              ? `The ${label} agent has not written anything for this case.`
              : `Nothing on file for the ${label} agent to read on this case.`}
          </p>
        ) : (
          <div className="flex flex-col gap-4">
            {parts.map(({ part, count }) => (
              <PartCard
                key={`${side}:${part.file}:${part.label}`}
                part={part}
                marks={marks}
                count={count}
              />
            ))}
          </div>
        )}
      </div>
    </>
  );
}

function PartCard({
  part,
  marks,
  count,
}: {
  part: HandoffPart;
  marks: ReadonlySet<number>;
  /** How many of the marked figures this block holds. */
  count: number;
}) {
  const [copied, setCopied] = useState(false);

  function copy() {
    void navigator.clipboard
      .writeText(JSON.stringify(part.data, null, 2))
      .then(() => {
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1400);
      });
  }

  return (
    <section className="overflow-hidden rounded-[10px] border border-line bg-panel">
      <div className="flex items-center justify-between gap-3 border-b border-divider bg-paper-sunk py-2 pr-2 pl-3.5">
        <div className="flex min-w-0 items-baseline gap-2">
          <span className="font-mono text-micro whitespace-nowrap text-ink">
            {part.file}
          </span>
          <span className="truncate text-meta text-faint-2">{part.label}</span>
          {count > 0 && (
            <span className="flex-none rounded-[4px] bg-accent-soft-2 px-1.5 py-px text-tiny font-medium whitespace-nowrap text-accent-dark">
              {count} marked
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={copy}
          className="flex-none cursor-pointer rounded-md border border-transparent bg-transparent px-2 py-1 text-tiny leading-none text-faint-2 transition-colors duration-[160ms] hover:bg-wash hover:text-ink"
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <div className="px-3.5 py-3">
        <JsonTree value={part.data} marks={marks} />
      </div>
    </section>
  );
}
