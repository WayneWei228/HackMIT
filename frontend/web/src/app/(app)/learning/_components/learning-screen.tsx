"use client";

import { useState } from "react";

import { Breadcrumb, Button, PageSubtitle, PageTitle } from "@/components/ui/primitives";
import { decideRule } from "@/lib/api";
import type { LearningView, MissLine, Person, RuleView } from "@/lib/api-types";
import { formatMoney, formatSigned } from "@/lib/money";
import { routes } from "@/lib/routes";
import { periodLabel } from "@/lib/time";
import { useApiAction } from "@/lib/use-api-action";

const FIELD =
  "w-full rounded-lg border border-line-warm bg-panel-hover px-[11px] py-[7px] text-sm leading-[1.4] text-ink outline-none focus-visible:shadow-[var(--shadow-ring-soft)]";

const STATUS_TONE: Record<string, { bg: string; fg: string; label: string }> = {
  REPLAY_PASSED: { bg: "#F2EDE4", fg: "#7A5A1E", label: "Waiting for the Controller" },
  ACTIVE: { bg: "#E9F0E5", fg: "#3C5840", label: "Active" },
  REJECTED: { bg: "#F0E4E0", fg: "#8A3A28", label: "Rejected" },
  REVOKED: { bg: "#F0E4E0", fg: "#8A3A28", label: "Revoked" },
  RULE_CANDIDATE: { bg: "#EDEBF2", fg: "#4A4660", label: "Candidate" },
};

const CRITERIA: Record<string, string> = {
  supporting_misses_improve: "Every miss the rule is meant to fix gets closer to its invoice",
  no_correct_estimate_flips: "No estimate that was right becomes wrong",
  total_error_falls: "Total error across all graded closes falls",
};

const CAUSES: Record<string, string> = {
  MISSED_ESCALATOR: "Missed price step-up",
  INCOMPLETE_DATA_EXTRAPOLATION: "Estimate projected from incomplete data",
  USAGE_VARIANCE: "Usage variance",
  SOURCE_DATA_ERROR: "Source data error",
  TIMING_DIFFERENCE: "Timing difference",
  UNKNOWN: "Unknown",
};

function purchaseTypes(rule: RuleView): string {
  const types = rule.predicate?.purchase_types;
  return Array.isArray(types)
    ? types.map((type) => String(type).toLowerCase().replaceAll("_", "-")).join(", ")
    : "matching";
}

function Heading({ children, sub }: { children: string; sub?: string }) {
  return (
    <div>
      <div className="font-display text-2xl text-ink-deep">{children}</div>
      {sub && <div className="mt-1.5 text-sm leading-[1.6] text-faint">{sub}</div>}
    </div>
  );
}

const cell = "border-b border-wash-deep py-[11px] pr-4 text-ui text-ink";

function Misses({ misses }: { misses: readonly MissLine[] }) {
  return (
    <section className="rounded-xl border border-divider bg-panel px-5 pt-5 pb-[18px] shadow-[var(--shadow-tile)]">
      <Heading sub="Each closed accrual was compared with the invoice that later arrived.">
        Graded closes
      </Heading>
      <div className="mt-4 grid grid-cols-[136px_1fr_110px_110px_170px_1.3fr] text-eyebrow font-medium tracking-caps-lg text-faint">
        {["PERIOD", "VENDOR", "ACCRUED", "INVOICED", "VARIANCE", "DIAGNOSIS"].map((label) => (
          <div key={label} className="border-b border-line pr-4 pb-[9px]">
            {label}
          </div>
        ))}
      </div>
      <div className="grid grid-cols-[136px_1fr_110px_110px_170px_1.3fr]">
        {misses.map((miss) => (
          <div key={miss.learning_id} className="contents">
            <div className={cell}>{periodLabel(miss.period)}</div>
            <div className={cell}>{miss.vendor_name}</div>
            <div className={`${cell} tabular-nums`}>{formatMoney(miss.accrued)}</div>
            <div className={`${cell} tabular-nums`}>{formatMoney(miss.actual)}</div>
            <div className={`${cell} tabular-nums text-accent`}>
              {formatSigned(miss.variance)}
              {miss.variance_percent ? ` (${miss.variance_percent}%)` : ""}
            </div>
            <div className={cell}>{CAUSES[miss.root_cause] ?? miss.root_cause}</div>
          </div>
        ))}
        {misses.length === 0 && (
          <div className="col-span-6 py-6 text-ui text-faint-2">No closes have been graded yet.</div>
        )}
      </div>
    </section>
  );
}

function RuleCard({ rule, people }: { rule: RuleView; people: readonly Person[] }) {
  const { run, pending, error } = useApiAction();
  const controller = people.find((p) => p.role === "Controller");
  const [actor, setActor] = useState(controller?.person_id ?? people[0]?.person_id ?? "");
  const [notes, setNotes] = useState("");
  const tone = STATUS_TONE[rule.status] ?? STATUS_TONE.RULE_CANDIDATE;
  const act = (action: "approve" | "reject" | "revoke") =>
    run(() => decideRule(rule.learning_id, action, { notes, decided_by: actor }));

  return (
    <section className="rounded-xl border border-divider bg-panel p-5 shadow-[var(--shadow-tile)]">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="text-sm text-faint-2">{rule.learning_id}</div>
          <div className="font-display mt-1 text-xl leading-[1.25] text-ink-deep">{rule.description}</div>
        </div>
        <span
          className="flex-none rounded-md px-2.5 py-[5px] text-meta whitespace-nowrap"
          style={{ background: tone.bg, color: tone.fg }}
        >
          {tone.label}
        </span>
      </div>

      <div className="mt-3.5 flex flex-wrap gap-x-6 gap-y-1.5 text-sm text-muted-4">
        <span>Supported by {rule.support} misses</span>
        <span>Applies to {purchaseTypes(rule)} purchases</span>
        <span>It never names a vendor</span>
        {rule.status === "ACTIVE" && (
          <span className="text-ink">
            {rule.stage === "CONFIRMED" ? "Confirmed" : "Provisional"}: {rule.uses} of 3 matching
            true-ups, {rule.contradictions} contradictions
          </span>
        )}
        {rule.approved_by && <span>Approved by {rule.approved_by}</span>}
      </div>

      <div className="mt-5 text-eyebrow font-medium tracking-caps-lg text-faint">
        REPLAY OVER EVERY GRADED CLOSE
      </div>
      <div className="mt-2.5 grid grid-cols-[136px_1fr_100px_100px_100px]">
        {["PERIOD", "VENDOR", "WITHOUT", "WITH RULE", "INVOICE"].map((label) => (
          <div key={label} className="border-b border-line pr-4 pb-2 text-eyebrow tracking-caps-lg text-faint">
            {label}
          </div>
        ))}
        {rule.replay.map((row) => (
          <div key={`${row.obligation_id}`} className="contents">
            <div className={cell}>{periodLabel(row.period)}</div>
            <div className={cell}>{row.vendor_name}</div>
            <div className={`${cell} tabular-nums`}>{formatMoney(row.before)}</div>
            <div className={`${cell} tabular-nums ${row.before !== row.after ? "text-accent" : ""}`}>
              {formatMoney(row.after)}
            </div>
            <div className={`${cell} tabular-nums`}>{formatMoney(row.actual)}</div>
          </div>
        ))}
      </div>
      {rule.total_error_before !== null && (
        <div className="mt-3 text-ui text-ink">
          Total error {formatMoney(rule.total_error_before)} to {formatMoney(rule.total_error_after)}
        </div>
      )}
      <div className="mt-3 flex flex-col gap-1.5">
        {Object.entries(rule.criteria).map(([key, ok]) => (
          <div key={key} className="flex items-center gap-2.5 text-sm text-ink-2">
            <span
              className="h-2 w-2 flex-none rounded-full"
              style={{ background: ok ? "#2E8047" : "#C2543D" }}
            />
            {CRITERIA[key] ?? key}
          </div>
        ))}
      </div>

      {(rule.can_approve || rule.can_reject || rule.can_revoke) && (
        <div className="mt-5 grid max-w-[560px] grid-cols-2 gap-x-3 gap-y-2 border-t border-wash-deep pt-4">
          <div>
            <label htmlFor={`actor-${rule.learning_id}`} className="text-meta text-muted-4">
              Acting as
            </label>
            <select
              id={`actor-${rule.learning_id}`}
              value={actor}
              onChange={(event) => setActor(event.target.value)}
              className={`${FIELD} mt-1`}
            >
              {people.map((person) => (
                <option key={person.person_id} value={person.person_id}>
                  {person.name} ({person.role})
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor={`notes-${rule.learning_id}`} className="text-meta text-muted-4">
              Notes (needed to reject or revoke)
            </label>
            <input
              id={`notes-${rule.learning_id}`}
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              className={`${FIELD} mt-1`}
            />
          </div>
          <div className="col-span-2 flex flex-wrap items-center gap-2.5">
            {rule.can_approve && (
              <Button
                variant="solid"
                disabled={pending}
                onClick={() => act("approve")}
                className="border border-accent px-3.5 text-[13.5px] leading-none hover:bg-accent-deep"
              >
                Approve the rule
              </Button>
            )}
            {rule.can_reject && (
              <Button
                variant="secondary"
                disabled={pending}
                onClick={() => act("reject")}
                className="px-3.5 text-[13.5px] leading-none"
              >
                Reject
              </Button>
            )}
            {rule.can_revoke && (
              <Button
                variant="secondary"
                disabled={pending}
                onClick={() => act("revoke")}
                className="px-3.5 text-[13.5px] leading-none"
              >
                Revoke
              </Button>
            )}
          </div>
        </div>
      )}
      {error && <div className="mt-3 text-meta leading-[1.5] text-[#A4452F]">{error}</div>}
    </section>
  );
}

/**
 * The learning loop: what the invoices showed the agents they got wrong, the
 * rule proposed from it, how it fared when replayed over history, and whether
 * the Controller has let it change tomorrow's estimates.
 */
export function LearningScreen({
  learning,
  people,
}: {
  learning: LearningView;
  people: readonly Person[];
}) {
  return (
    <main className="flex min-w-[900px] flex-1 flex-col overflow-hidden leading-[normal]">
      <div className="flex-none px-[34px] pt-[26px]">
        <Breadcrumb items={[{ label: "CLOSE", href: routes.cases }, { label: "LEARNING" }]} />
        <PageTitle className="text-[46px]/[1.05]">Learning</PageTitle>
        <PageSubtitle>
          Every rule is graded by the invoice, replay-tested on past closes and approved by the
          Controller before it changes an estimate.
        </PageSubtitle>
      </div>
      <div className="mt-6 min-h-0 flex-1 overflow-y-auto px-[34px] pb-[30px]">
        <div className="flex flex-col gap-3.5">
          <Misses misses={learning.misses} />
          {learning.rules.length === 0 && (
            <div className="rounded-xl border border-divider bg-panel px-5 py-8 text-ui text-faint-2">
              No rule has been proposed yet. A rule needs at least two graded misses with the same
              cause.
            </div>
          )}
          {learning.rules.map((rule) => (
            <RuleCard key={rule.learning_id} rule={rule} people={people} />
          ))}
        </div>
      </div>
    </main>
  );
}
