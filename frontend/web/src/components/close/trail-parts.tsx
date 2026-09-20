import type { LogEntry, LogMethod, LogSource, RuleTest } from "@/lib/api-types";
import { cn } from "@/lib/cn";

const METHODS: Record<LogMethod, { label: string; chip: string }> = {
  CODE: { label: "Rule-based code", chip: "bg-wash text-muted-3" },
  LLM: { label: "Language model", chip: "bg-[#EDE8F5] text-[#5B4A86]" },
  HUMAN: { label: "Human action", chip: "bg-[#F6ECD3] text-[#8A6516]" },
};

/** Says whether a step was fixed rules, a language model or a person - only when the entry says so. */
export function MethodTag({ method }: { method: LogMethod | null | undefined }) {
  if (!method) return null;
  const style = METHODS[method];
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-sm px-1.5 py-[3px] text-nano leading-none font-medium",
        style.chip,
      )}
    >
      {style.label}
    </span>
  );
}

/** Ties an entry to the database row it was read from. */
export function RunTag({ runId, prefix = "live from run log" }: { runId?: number | null; prefix?: string }) {
  if (runId === undefined || runId === null) return null;
  return (
    <span className="font-mono text-nano whitespace-nowrap text-ghost">
      {prefix} #{runId}
    </span>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-1 text-nano font-semibold tracking-caps text-faint-2">{children}</div>
  );
}

export function SourcesList({ sources }: { sources: LogSource[] }) {
  if (sources.length === 0) return null;
  return (
    <div>
      <Label>SOURCES READ</Label>
      <ul className="flex flex-col gap-1.5">
        {sources.map((source, index) => (
          <li key={`${source.file_name}-${index}`} className="min-w-0">
            <div className="flex flex-wrap items-baseline gap-x-2">
              <span className="text-meta font-medium break-words text-ink-2">{source.file_name}</span>
              {source.evidence_id && (
                <span className="font-mono text-nano text-ghost">{source.evidence_id}</span>
              )}
            </div>
            {source.quote && (
              <blockquote className="mt-0.5 border-l-2 border-accent-line pl-2 text-meta leading-[1.55] break-words text-muted-3 italic">
                &ldquo;{source.quote}&rdquo;
              </blockquote>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function RulesList({ rules }: { rules: RuleTest[] }) {
  if (rules.length === 0) return null;
  return (
    <div>
      <Label>RULES EVALUATED</Label>
      <ul className="flex flex-col gap-1">
        {rules.map((rule) => (
          <li key={rule.rule_id} className="flex min-w-0 items-baseline gap-2">
            <span
              className={cn(
                "flex-none rounded-sm px-1 py-[2px] font-mono text-nano leading-none font-medium",
                rule.fired ? "bg-[#F6ECD3] text-[#8A6516]" : "bg-wash text-muted-3",
              )}
            >
              {rule.rule_id}
            </span>
            <span className="flex-none text-nano font-medium text-faint-2">
              {rule.fired ? "fired" : "did not fire"}
            </span>
            <span className="min-w-0 text-meta break-words text-ink-3">{rule.sentence}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function isPlain(value: unknown): value is string | number | boolean {
  return ["string", "number", "boolean"].includes(typeof value);
}

/** What an entry read and was unsure about, with the row ids it consumed and produced. */
export function EntryDetail({ entry }: { entry: LogEntry }) {
  const { detail } = entry;
  const facts = detail.facts_used ?? [];
  return (
    <div className="mt-2 flex flex-col gap-3 rounded-lg border border-line bg-panel px-3 py-2.5">
      <SourcesList sources={detail.sources ?? []} />
      <RulesList rules={detail.rules ?? []} />
      {facts.length > 0 && (
        <div>
          <Label>FACTS USED</Label>
          <ul className="flex flex-col gap-1 font-mono text-tiny text-ink-3">
            {facts.map((fact, index) => (
              <li key={index} className="break-words">
                {isPlain(fact) ? String(fact) : JSON.stringify(fact)}
              </li>
            ))}
          </ul>
        </div>
      )}
      {(detail.uncertainties ?? []).length > 0 && (
        <div>
          <Label>UNCERTAINTIES</Label>
          <ul className="list-disc pl-4 text-meta text-[#8A6516]">
            {detail.uncertainties.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      )}
      {((detail.input_ids ?? []).length > 0 || (detail.output_ids ?? []).length > 0) && (
        <div className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 font-mono text-nano text-muted-4">
          {(detail.input_ids ?? []).length > 0 && (
            <>
              <span className="text-ghost">read</span>
              <span className="break-words">{detail.input_ids.join(", ")}</span>
            </>
          )}
          {(detail.output_ids ?? []).length > 0 && (
            <>
              <span className="text-ghost">wrote</span>
              <span className="break-words">{detail.output_ids.join(", ")}</span>
            </>
          )}
        </div>
      )}
      {facts.length === 0 &&
        !detail.sources?.length &&
        !detail.rules?.length &&
        (detail.uncertainties ?? []).length === 0 &&
        (detail.input_ids ?? []).length === 0 &&
        (detail.output_ids ?? []).length === 0 && (
          <div className="text-meta text-faint-2">The run log holds no further detail for this step.</div>
        )}
    </div>
  );
}
