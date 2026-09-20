"use client";

import { useEffect, useState } from "react";

import type { CloseView, ModelHealth } from "@/lib/api-types";
import { caseData, useClose } from "@/lib/case-data";
import { cn } from "@/lib/cn";

const REFRESH_MS = 30_000;
const WARN_MINUTES = 60;

type Tone = "live" | "warn" | "down" | "idle";

const DOT: Record<Tone, string> = {
  live: "#2E8047",
  warn: "#D6A43C",
  down: "#C2543D",
  idle: "#B9BFB3",
};

const TEXT: Record<Tone, string> = {
  live: "text-muted-3",
  warn: "text-[#8A6420]",
  down: "font-medium text-[#A4452F]",
  idle: "text-faint-2",
};

const USING_RULES = "Model unavailable - agents are using rules";

function minutesUntil(iso: string, now: number): number {
  return Math.floor((Date.parse(iso) - now) / 60_000);
}

function describe(
  model: ModelHealth,
  now: number | null,
): { tone: Tone; label: string; reason: string | null } {
  if (model.mode === "offline") {
    return { tone: "idle", label: "Model offline - agents use rules", reason: null };
  }
  if (model.status === "credentials_rejected") {
    return { tone: "down", label: USING_RULES, reason: "Credentials rejected. Refresh the Bedrock key." };
  }
  if (model.status === "unavailable") {
    return { tone: "down", label: USING_RULES, reason: "The model is not responding." };
  }
  const left = model.expires_at && now !== null ? minutesUntil(model.expires_at, now) : null;
  if (left !== null && left <= 0) {
    return { tone: "down", label: USING_RULES, reason: "The Bedrock key has expired." };
  }
  if (model.status === "unknown") {
    return { tone: "idle", label: "Checking the model...", reason: null };
  }
  if (left !== null && left <= WARN_MINUTES) {
    return { tone: "warn", label: `Model expires in ${left} min`, reason: null };
  }
  return { tone: "live", label: "Model live", reason: null };
}

function detail(model: ModelHealth): string {
  const lines = [`Mode: ${model.mode}`, `Status: ${model.status}`];
  if (model.last_ok_at) lines.push(`Last successful call: ${model.last_ok_at}`);
  if (model.expires_at) {
    lines.push(`The key states it works until ${model.expires_at} at the latest.`);
  }
  if (model.last_error) lines.push(`Last error: ${model.last_error}`);
  return lines.join("\n");
}

/**
 * A quiet line in the sidebar saying whether the language model is answering, so a lapsed key
 * shows here at once and not as a case that quietly ran on its rules.
 */
export function ModelStatus({ initial }: { initial: CloseView | null }) {
  const close = useClose(initial);
  const [now, setNow] = useState<number | null>(null);

  useEffect(() => {
    const tick = () => {
      setNow(Date.now());
      void caseData.refreshClose();
    };
    const first = setTimeout(() => setNow(Date.now()), 0);
    const timer = setInterval(tick, REFRESH_MS);
    return () => {
      clearTimeout(first);
      clearInterval(timer);
    };
  }, []);

  const model = close?.model;
  if (!model) return null;
  const { tone, label, reason } = describe(model, now);

  return (
    <section aria-label="Model status" title={detail(model)} className="px-[22px] pt-2 pb-3">
      <div className="flex items-start gap-2">
        <span
          aria-hidden="true"
          className="mt-[5px] h-2 w-2 flex-none rounded-full"
          style={{ background: DOT[tone] }}
        />
        <span
          role={tone === "down" ? "alert" : "status"}
          className={cn("min-w-0 text-meta leading-[1.3] text-pretty", TEXT[tone])}
        >
          {label}
        </span>
      </div>
      {reason && (
        <div className="mt-0.5 pl-4 text-meta leading-[1.35] text-faint-2 text-pretty">{reason}</div>
      )}
    </section>
  );
}
