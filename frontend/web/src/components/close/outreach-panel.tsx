"use client";

import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "motion/react";

import { CloseIcon, MailIcon } from "@/components/ui/icons";
import { Button } from "@/components/ui/primitives";
import type {
  OutreachThread,
  ThreadMessage,
  ThreadParsed,
} from "@/lib/api-types";
import { useCaseId } from "@/lib/case-context";
import { cn } from "@/lib/cn";
import { formatMoney } from "@/lib/money";
import { transitions } from "@/lib/motion";
import { outreachPanel, useOutreachPanel } from "@/lib/outreach-panel";
import { formatStamp } from "@/lib/time";

import { VerdictChip } from "./gate";
import {
  counterpartOf,
  statusOf,
  topicLabel,
  useOutreachThreads,
} from "./outreach-thread";
import { momentLabel, useTimeAction } from "./time-action";

const METHOD_CHIPS: Record<
  ThreadMessage["method"],
  { label: string; chip: string }
> = {
  LLM: {
    label: "Written by the language model",
    chip: "bg-[#EDE8F5] text-[#5B4A86]",
  },
  TEMPLATE: { label: "Template draft", chip: "bg-wash text-muted-3" },
  SCRIPTED_REPLY: {
    label: "Synthetic reply",
    chip: "bg-[#F6ECD3] text-[#8A6516]",
  },
};

const FACT_LABELS: Record<string, string> = {
  quantity: "Quantity",
  unit: "Unit",
  in_service_date: "In-service date",
  service_received: "Service received",
  corrected_amount: "Corrected amount",
};

function stampOf(iso: string | null): string | null {
  if (!iso) return null;
  const { date, time } = formatStamp(iso);
  return `${date}, ${time}`;
}

function factValue(key: string, value: string): string {
  if (key === "corrected_amount") return formatMoney(value);
  if (key === "quantity" && /^\d+(\.\d+)?$/.test(value))
    return Number(value).toLocaleString("en-US");
  return value;
}

function Party({
  label,
  name,
  role,
}: {
  label: string;
  name: string;
  role: string;
}) {
  return (
    <div className="flex items-baseline gap-2 text-ui leading-[1.4]">
      <span className="w-[34px] flex-none text-meta text-faint-2">{label}</span>
      <span className="min-w-0 text-ink">
        {name}
        {role && <span className="text-faint-2"> - {role}</span>}
      </span>
    </div>
  );
}

function Message({ message }: { message: ThreadMessage }) {
  const outgoing = message.direction === "OUT";
  const chip = METHOD_CHIPS[message.method];
  return (
    <motion.article
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={transitions.base}
      className={cn(
        "rounded-xl border p-4 shadow-[var(--shadow-tile)]",
        outgoing
          ? "border-divider bg-panel"
          : "border-accent-line-2 bg-accent-tint",
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <span className="text-eyebrow font-medium tracking-caps text-faint uppercase">
          {outgoing ? "Sent" : "Reply received"}
        </span>
        <span className="text-meta text-faint-2 tabular-nums">
          {stampOf(message.at)}
        </span>
      </div>
      <div className="mt-2.5 flex flex-col gap-1">
        <Party label="From" name={message.from.name} role={message.from.role} />
        <Party label="To" name={message.to.name} role={message.to.role} />
      </div>
      <div className="mt-3.5 border-t border-line pt-3.5 font-display text-[19px] leading-[1.25] text-ink-deep text-balance">
        {message.subject}
      </div>
      <div className="mt-2.5 text-ui leading-[1.6] whitespace-pre-wrap text-ink-2">
        {message.body}
      </div>
      <div className="mt-3.5 flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
        <span
          className={cn(
            "inline-flex items-center rounded-sm px-1.5 py-[3px] text-nano leading-none font-medium",
            chip.chip,
          )}
        >
          {chip.label}
        </span>
        {message.run_id !== null && (
          <span className="font-mono text-nano text-ghost">
            run #{message.run_id}
          </span>
        )}
      </div>
    </motion.article>
  );
}

/** The email is out; its answer comes when the presenter sends the synthetic reply, for this case alone. */
function ReplyButton() {
  const { action, others, take, pending, error } = useTimeAction();
  if (!action || action.kind === "BRING_IN_INVOICE") return null;
  return (
    <div className="flex flex-col items-start gap-2.5">
      <div
        data-slot="outreach-actions"
        className="flex flex-wrap items-center gap-2.5"
      >
        <Button
          variant="solid"
          disabled={pending}
          onClick={() => void take(action)}
        >
          {pending ? "Working..." : action.label}
        </Button>
        {others.map((other) => (
          <Button
            key={other.kind}
            variant="secondary"
            disabled={pending}
            onClick={() => void take(other)}
          >
            {other.label}
          </Button>
        ))}
      </div>
      <div className="text-meta leading-[1.45] text-faint-2">
        {action.detail} Moves this case to {momentLabel(action.moves_to)}; no
        other case is touched.
        {others.map((other) => ` ${other.detail}`).join("")}
      </div>
      {error && <div className="text-meta text-[#A4452F]">{error}</div>}
    </div>
  );
}

/** After a path is taken, the same two scenarios stay one click away, from this panel too. */
function OtherScenario() {
  const { canRewind, otherPath, tryOther, rewind, pending, error } =
    useTimeAction();
  if (!canRewind) return null;
  return (
    <div className="flex flex-col items-start gap-2.5 rounded-xl border border-divider bg-panel p-4">
      <div className="text-eyebrow font-medium tracking-caps text-faint uppercase">
        The other scenario
      </div>
      <div className="flex flex-wrap items-center gap-2.5">
        {otherPath && (
          <Button
            variant="solid"
            disabled={pending}
            onClick={() => void tryOther()}
          >
            {pending ? "Working..." : "Try the other scenario"}
          </Button>
        )}
        <Button
          variant="secondary"
          disabled={pending}
          onClick={() => void rewind()}
        >
          Rewind to the email
        </Button>
      </div>
      {otherPath && (
        <div className="text-meta leading-[1.45] text-faint-2">
          {otherPath.detail} Moves this case to{" "}
          {momentLabel(otherPath.moves_to)}; no other case is touched.
        </div>
      )}
      {pending && (
        <div className="text-meta text-faint-2">
          Replaying this case from day one with the live model. This can take up
          to a minute.
        </div>
      )}
      {error && <div className="text-meta text-[#A4452F]">{error}</div>}
    </div>
  );
}

function Waiting({ thread }: { thread: OutreachThread }) {
  const waiting = thread.waiting_on;
  const due = stampOf(thread.due_at);
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={transitions.base}
      className="rounded-xl border border-dashed border-line-dark bg-wash-warm/60 p-4"
    >
      <div className="flex items-center gap-2.5 text-ui font-medium text-ink">
        <span className="relative flex h-[9px] w-[9px] flex-none">
          <span className="animate-pulse-ring absolute inset-0 rounded-full bg-[#D6A43C] opacity-50" />
          <span className="relative h-[9px] w-[9px] rounded-full bg-[#D6A43C]" />
        </span>
        Waiting on {waiting ? waiting.name : "a reply"}
      </div>
      <div className="mt-1.5 mb-3.5 text-meta leading-[1.5] text-muted-3">
        No reply yet.
        {due ? ` A reply is due by ${due}.` : ""} The case is paused until it
        arrives; in this demo the reply is scripted and lands when you send the
        synthetic reply.
      </div>
      <ReplyButton />
    </motion.div>
  );
}

function ParsedReply({
  parsed,
  thread,
}: {
  parsed: ThreadParsed;
  thread: OutreachThread;
}) {
  const facts = Object.entries(parsed.facts);
  const gate = thread.verification;
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ ...transitions.base, delay: 0.08 }}
      className="rounded-xl border border-divider bg-panel p-4"
    >
      <div className="flex items-center justify-between gap-3">
        <span className="text-eyebrow font-medium tracking-caps text-faint uppercase">
          What the Outreach agent read
        </span>
        <span
          className={cn(
            "rounded-sm px-1.5 py-[3px] text-nano leading-none font-semibold tracking-caps",
            parsed.resolved
              ? "bg-accent-soft text-accent-deep"
              : "bg-[#F6E4DD] text-[#A4452F]",
          )}
        >
          {parsed.resolved ? "ENOUGH TO CONTINUE" : "NOT ENOUGH"}
        </span>
      </div>
      {facts.length > 0 && (
        <dl className="mt-3 flex flex-col gap-1.5 text-ui">
          {facts.map(([key, value]) => (
            <div key={key} className="flex justify-between gap-4">
              <dt className="text-faint-2">{FACT_LABELS[key] ?? key}</dt>
              <dd className="font-medium text-ink tabular-nums">
                {factValue(key, value)}
              </dd>
            </div>
          ))}
        </dl>
      )}
      {parsed.note && (
        <div className="mt-3 text-meta leading-[1.5] text-muted-3 text-pretty">
          {parsed.note}
        </div>
      )}
      <div className="mt-3 border-t border-line pt-3 text-meta leading-[1.5] text-muted-3">
        {parsed.resolved
          ? "The reply covered what was asked, so the case picked up again where it paused."
          : "The reply did not cover what was asked, so the case was routed to the Controller instead of being guessed."}
      </div>
      {gate && (
        <div className="mt-2.5 flex items-center gap-2 text-meta text-muted-3">
          <VerdictChip verdict={gate.verdict} />
          {gate.passed}/{gate.total} checks passed at the handoff after the
          reply
        </div>
      )}
    </motion.div>
  );
}

function ThreadView({ thread }: { thread: OutreachThread }) {
  const replied = thread.messages.some((message) => message.direction === "IN");
  const state = statusOf(thread);
  const sent = stampOf(thread.sent_at);
  return (
    <div className="flex flex-col gap-3.5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-meta text-muted-3">
        <span className="inline-flex items-center gap-1.5 font-medium text-ink">
          <span
            className="h-[7px] w-[7px] rounded-full"
            style={{ background: state.mark }}
          />
          {state.text}
        </span>
        {sent && <span className="tabular-nums">Sent {sent}</span>}
        <span>{topicLabel(thread.topic)}</span>
      </div>
      {thread.messages.map((message) => (
        <Message
          key={message.evidence_id ?? `${message.direction}-${message.at}`}
          message={message}
        />
      ))}
      {!replied && thread.waiting_on && <Waiting thread={thread} />}
      {thread.parsed && <ParsedReply parsed={thread.parsed} thread={thread} />}
      <OtherScenario />
    </div>
  );
}

function Panel({
  obligationId,
  threadId,
}: {
  obligationId: string;
  threadId: string | null;
}) {
  const threads = useOutreachThreads(obligationId);
  const thread = threads.find((t) => t.thread_id === threadId) ?? threads[0];
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") outreachPanel.close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <>
      <motion.div
        key="scrim"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={transitions.fast}
        className="fixed inset-0 z-40 bg-ink-deep/10"
        onClick={() => outreachPanel.close()}
      />
      <motion.aside
        key="panel"
        role="dialog"
        aria-label="Emails on this case"
        initial={{ x: 28, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        exit={{ x: 28, opacity: 0 }}
        transition={transitions.base}
        className="fixed top-0 right-0 bottom-0 z-50 flex w-[560px] max-w-full flex-col border-l border-divider bg-paper-sunk shadow-[var(--shadow-pop)]"
      >
        <header className="flex-none border-b border-divider bg-panel px-6 pt-5 pb-4">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="text-eyebrow font-medium tracking-caps text-faint uppercase">
                Outreach
              </div>
              <div className="mt-1.5 truncate font-display text-[26px] leading-[1.1] text-ink-deep">
                {thread
                  ? `Email to ${counterpartOf(thread)}`
                  : "No emails on this case"}
              </div>
            </div>
            <button
              ref={closeRef}
              type="button"
              aria-label="Close the emails"
              onClick={() => outreachPanel.close()}
              className="flex h-8 w-8 flex-none cursor-pointer items-center justify-center rounded-lg text-muted-3 transition-colors duration-[160ms] hover:bg-wash hover:text-ink focus-visible:shadow-[var(--shadow-ring)] focus-visible:outline-none"
            >
              <CloseIcon />
            </button>
          </div>
          <div className="mt-3 inline-flex items-center gap-2 rounded-md bg-[#F6ECD3] px-2.5 py-1.5 text-meta text-[#8A6516]">
            <MailIcon size={13} />
            Synthetic email - nothing is really sent
          </div>
          {threads.length > 1 && (
            <div className="mt-3.5 flex flex-wrap gap-1.5">
              {threads.map((t) => (
                <button
                  key={t.thread_id}
                  type="button"
                  onClick={() => outreachPanel.select(t.thread_id)}
                  className={cn(
                    "cursor-pointer rounded-lg border px-3 py-1.5 text-meta transition-colors duration-[160ms]",
                    t.thread_id === thread?.thread_id
                      ? "border-accent-line bg-accent-tint text-accent-deep"
                      : "border-line-soft bg-panel text-muted-3 hover:bg-panel-hover",
                  )}
                >
                  {counterpartOf(t)} - {topicLabel(t.topic)}
                </button>
              ))}
            </div>
          )}
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
          {thread ? (
            <ThreadView key={thread.thread_id} thread={thread} />
          ) : (
            <div className="text-ui text-faint-2">
              This case has not needed to ask anyone anything.
            </div>
          )}
        </div>
      </motion.aside>
    </>
  );
}

/** The slide-in inbox for a case's emails. Mounted once per case screen; anything can open it. */
export function OutreachPanel() {
  const id = useCaseId();
  const open = useOutreachPanel();
  const showing = open !== null && open.obligationId === id;
  if (typeof document === "undefined") return null;
  return createPortal(
    <AnimatePresence>
      {showing && (
        <Panel
          key="outreach"
          obligationId={open.obligationId}
          threadId={open.threadId}
        />
      )}
    </AnimatePresence>,
    document.body,
  );
}
