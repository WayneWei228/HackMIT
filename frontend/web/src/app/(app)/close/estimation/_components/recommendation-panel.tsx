"use client";

import { ViewEmailLink } from "@/components/close/outreach-strip";

import { ConfirmIcon } from "./icons";
import { useEstimationScreen } from "./screen-context";

/** Right column: the number the agent landed on and the entry it implies, from the workpaper. */
export function RecommendationPanel() {
  const { amount, recommendation, note, journal, hasEstimate, fallback } = useEstimationScreen();

  return (
    <section className="min-h-full rounded-xl border border-divider bg-panel p-5 shadow-[var(--shadow-tile)]">
      <div className="border-b border-divider-3 pb-3.5">
        <div className="font-display text-2xl leading-[normal] text-ink-deep">Recommended accrual</div>
      </div>

      <div className="mt-[18px] text-ui leading-[normal] text-ink-2">Accrual amount</div>
      <div className="font-display mt-1.5 min-h-[50px] text-[34px] leading-[1.1] whitespace-nowrap text-ink-deep 2xl:text-[44px]">
        {amount}
      </div>

      <div className="mt-[18px] flex flex-col">
        {recommendation.map((row) => (
          <div
            key={row.label}
            className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)] items-center gap-x-3.5 border-t border-wash-deep py-[11px]"
          >
            <span className="min-w-0 text-ui leading-[normal] text-muted-4">{row.label}</span>
            <span
              className={`min-w-0 text-right text-ui leading-[normal] break-words ${
                row.tone === "accent" ? "text-accent" : "text-ink"
              }`}
            >
              {row.value}
            </span>
          </div>
        ))}
      </div>

      {fallback && (
        <div
          data-slot="incomplete-data-estimate"
          className="mt-5 rounded-lg border border-[#EBD9A8] bg-[#FBF5E6] px-3.5 py-[13px] text-meta leading-[1.6] text-[#8A6516]"
        >
          <div className="text-eyebrow font-medium tracking-caps uppercase">
            Made on incomplete data, no reply came
          </div>
          <div className="mt-1.5 font-medium text-[#6B520F]">
            {fallback.kind === "RECEIPT"
              ? "Reply did not arrive by the deadline; the quantity received is estimated"
              : `Reply did not arrive by the deadline; estimate built from ${fallback.coverage}`}
          </div>
          <dl className="mt-2.5 flex flex-col gap-1.5 text-[#6B520F]">
            <FallbackRow label="Method" value={fallback.method_label} />
            <FallbackRow
              label="Chosen by"
              value={fallback.chosen_by === "LLM" ? "Language model" : "Rule-based code"}
            />
            <FallbackRow
              label={fallback.kind === "RECEIPT" ? "Basis" : "Data covers"}
              value={fallback.coverage}
            />
            <FallbackRow label="Confidence" value={fallback.confidence} />
          </dl>
          <div className="mt-2.5 text-pretty">{fallback.definition}</div>
          {fallback.assumption && (
            <div className="mt-2 text-pretty font-medium">Assumption: {fallback.assumption}</div>
          )}
          {fallback.rationale && <div className="mt-2 text-pretty">Why: {fallback.rationale}</div>}
          {fallback.rejected.map((other) => (
            <div key={other.method} className="mt-1 text-pretty">
              Not used, {other.method}: {other.reason}
            </div>
          ))}
          <div className="mt-2.5 font-medium">The Controller must approve this estimate.</div>
        </div>
      )}

      {note && (
        <div
          className={`mt-5 flex items-start gap-[11px] rounded-lg px-3.5 py-[13px] ${
            hasEstimate ? "bg-accent-tint" : "border border-[#EBD9A8] bg-[#FBF5E6]"
          }`}
        >
          {hasEstimate && <ConfirmIcon className="mt-px flex-none" />}
          <div
            className={`min-w-0 text-meta leading-[1.65] text-pretty break-words ${
              hasEstimate ? "text-accent-slate" : "text-[#8A6516]"
            }`}
          >
            {note}
            {!hasEstimate && <ViewEmailLink className="mt-2.5 flex" label="View the email that was sent" />}
          </div>
        </div>
      )}

      {journal.length > 0 && (
        <div className="mt-[22px]">
          <div className="text-ui leading-[normal] text-ink-2">Journal preview</div>
          <div className="mt-3 grid grid-cols-[22px_minmax(0,1fr)_auto] gap-2.5 text-sm leading-[normal] text-ink">
            {journal.map((line) => (
              <div key={`${line.side}-${line.account}`} className="contents">
                <span className="text-faint-2">{line.side}</span>
                <span className="min-w-0 break-words">{line.account}</span>
                <span className="text-right tabular-nums">{line.amount}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function FallbackRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4">
      <dt>{label}</dt>
      <dd className="text-right font-medium">{value}</dd>
    </div>
  );
}
