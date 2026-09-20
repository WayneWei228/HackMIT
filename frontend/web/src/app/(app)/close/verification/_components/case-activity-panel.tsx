"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { formatMoney, formatSigned } from "@/lib/money";
import { routes } from "@/lib/routes";

import { useVerificationScreen } from "./screen-context";

function Block({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="text-eyebrow font-medium tracking-caps-lg text-faint">{title}</div>
      <div className="mt-3">{children}</div>
    </div>
  );
}

function Pair({ label, value, tone }: { label: string; value: string; tone?: "accent" }) {
  return (
    <div className="flex items-center justify-between gap-3.5 border-t border-wash-deep py-[10px] first:border-t-0">
      <span className="text-ui text-muted-4">{label}</span>
      <span className={`text-right text-ui tabular-nums ${tone === "accent" ? "text-accent" : "text-ink"}`}>
        {value}
      </span>
    </div>
  );
}

const AUDIT_DOT = {
  PASS: "#2E8047",
  NOTE: "#D6A43C",
  FAIL: "#C2543D",
  NOT_APPLICABLE: "#C0C5BB",
} as const;

const CAUSES: Record<string, string> = {
  MISSED_ESCALATOR: "The estimate missed a price step-up",
  INCOMPLETE_DATA_EXTRAPOLATION: "The estimate was projected from incomplete data",
  USAGE_VARIANCE: "Usage differed from the estimate",
  SOURCE_DATA_ERROR: "The invoice does not match what was delivered",
  TIMING_DIFFERENCE: "Timing difference",
  UNKNOWN: "Unknown cause",
};

/**
 * What happened to the case after the checks: the Controller's review, any
 * request to the service owner, the January invoice that graded the accrual,
 * and the entries posted. Blocks appear only when the case has that history.
 */
export function CaseActivityPanel() {
  const view = useVerificationScreen();
  const { controller, reconciliation, outreach, rulesApplied, entries, audit } = view;
  const blocks: ReactNode[] = [];

  if (controller.in_queue || controller.record) {
    blocks.push(
      <Block key="controller" title="CONTROLLER REVIEW">
        {controller.in_queue && (
          <>
            <p className="text-sm leading-[1.65] text-pretty text-ink-2">{controller.narrative}</p>
            <p className="mt-2.5 text-sm leading-[1.65] text-pretty text-muted-4">
              {controller.recommendation}
            </p>
          </>
        )}
        {controller.record && (
          <div className="mt-3 rounded-lg bg-rail-alt px-3.5 py-3 text-sm leading-[1.6] text-ink-2">
            <span className="font-medium text-ink">{controller.record.decision.replaceAll("_", " ")}</span>{" "}
            by {controller.record.decided_by}
            {controller.record.notes ? `: ${controller.record.notes}` : "."}
          </div>
        )}
      </Block>,
    );
  }

  if (reconciliation) {
    blocks.push(
      <Block key="reconciliation" title="JANUARY INVOICE GRADED THE ACCRUAL">
        <Pair label="Accrued" value={formatMoney(reconciliation.accrued)} />
        <Pair label="Invoiced" value={formatMoney(reconciliation.actual)} />
        <Pair
          label="Variance"
          value={formatSigned(reconciliation.variance)}
          tone={reconciliation.root_cause ? "accent" : undefined}
        />
        {reconciliation.root_cause && (
          <Pair
            label="Diagnosis"
            value={CAUSES[reconciliation.root_cause] ?? reconciliation.root_cause}
          />
        )}
        <p className="mt-2.5 text-sm leading-[1.65] text-pretty text-muted-4">
          {reconciliation.explanation}
        </p>
      </Block>,
    );
  }

  if (outreach.length > 0) {
    blocks.push(
      <Block key="outreach" title="OUTREACH TO THE SERVICE OWNER">
        <div className="flex flex-col gap-3">
          {outreach.map((message, index) => (
            <div
              key={`${message.direction}-${index}`}
              className="rounded-lg bg-rail-alt px-3.5 py-3 text-sm leading-[1.6] text-ink-2"
            >
              <div className="text-micro text-faint-2">
                {message.direction === "REQUEST" ? `Asked ${message.to ?? ""}` : "Reply"} · {message.status}
              </div>
              {message.subject && <div className="mt-1 font-medium text-ink">{message.subject}</div>}
              <div className="mt-1 whitespace-pre-wrap">{message.body}</div>
            </div>
          ))}
        </div>
      </Block>,
    );
  }

  if (rulesApplied.length > 0) {
    blocks.push(
      <Block key="rules" title="LEARNED RULE APPLIED">
        {rulesApplied.map((rule) => (
          <div key={rule.learning_id} className="text-sm leading-[1.65] text-ink-2">
            <Link href={routes.learning} className="font-medium text-accent-link hover:underline">
              {rule.learning_id}
            </Link>{" "}
            ({rule.status.toLowerCase()}): {rule.description}
          </div>
        ))}
      </Block>,
    );
  }

  if (entries.length > 0) {
    blocks.push(
      <Block key="entries" title="JOURNAL ENTRIES">
        <div className="flex flex-col gap-3">
          {entries.map((entry) => (
            <div key={entry.entry_id} className="rounded-lg bg-rail-alt px-3.5 py-3">
              <div className="text-micro text-faint-2">
                {entry.entry_type.replaceAll("_", " ")} · {entry.period}
                {entry.posting_date ? ` · ${entry.posting_date}` : ""}
              </div>
              <div className="mt-2 grid grid-cols-[22px_1fr_auto] gap-2.5 text-sm text-ink">
                {entry.lines.map((line) => (
                  <div key={`${entry.entry_id}-${line.side}-${line.account}`} className="contents">
                    <span className="text-faint-2">{line.side}</span>
                    <span>
                      {line.account} {line.account_name && `· ${line.account_name}`}
                    </span>
                    <span className="text-right tabular-nums">{formatMoney(line.amount)}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Block>,
    );
  }

  const audited = audit?.obligations[0];
  if (audit && audited) {
    blocks.push(
      <Block key="audit" title="INDEPENDENT AUDIT">
        <p className="text-sm leading-[1.65] text-pretty text-muted-4">{audit.summary}</p>
        <div className="mt-3 flex flex-col gap-2">
          {audited.controls.map((control) => (
            <div key={control.check_id} className="flex items-start gap-2.5 text-sm text-ink-2">
              <span
                className="mt-[6px] h-2 w-2 flex-none rounded-full"
                style={{ background: AUDIT_DOT[control.status] }}
              />
              <span className="min-w-0">
                <span className="text-faint-2">{control.check_id}</span> {control.name}
                <span className="block text-meta text-faint-2">{control.detail}</span>
              </span>
            </div>
          ))}
          {audited.findings.map((finding) => (
            <div key={finding.finding_id} className="rounded-lg bg-rail-alt px-3.5 py-2.5 text-sm text-ink-2">
              <span className="font-medium text-ink">{finding.severity}</span> {finding.message}
            </div>
          ))}
        </div>
      </Block>,
    );
  }

  if (blocks.length === 0) return null;

  return (
    <section className="mt-[14px] rounded-xl border border-divider bg-panel px-5 pt-5 pb-[22px] shadow-[var(--shadow-tile)]">
      <div className="font-display text-2xl text-ink-deep">Case activity</div>
      <div className="mt-1.5 border-b border-divider-3 pb-[14px] text-sm leading-[1.6] text-faint">
        What happened to this accrual after the checks.
      </div>
      <div className="mt-5 grid grid-cols-[repeat(auto-fit,minmax(300px,1fr))] gap-x-8 gap-y-7">
        {blocks}
      </div>
    </section>
  );
}
