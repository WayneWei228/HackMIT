"use client";

import { NoteInfoIcon } from "./glyphs";
import { Panel, PanelHeading } from "./panel";
import { useObligationScreen } from "./screen-context";

/**
 * Right column: the number the agent stands behind, the terms it rests on, and
 * the reasoning it recorded. The amount is a dash until Estimation has produced
 * it.
 */
export function ConclusionPanel() {
  const { conclusion, rows } = useObligationScreen();

  return (
    <Panel className="p-5">
      <div className="flex items-center justify-between gap-2.5 border-b border-divider-3 pb-3.5">
        <PanelHeading>Provisional conclusion</PanelHeading>
      </div>

      <div className="mt-[18px] text-ui text-ink-2">{conclusion.amountLabel}</div>
      <div className="font-display mt-1.5 min-h-[50px] text-[44px] leading-[1.1] break-words text-ink-deep">
        {conclusion.amount}
      </div>

      <div className="mt-[18px] flex flex-col">
        {rows.map((row) => (
          <div
            key={row.label}
            className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] items-center gap-x-3.5 border-t border-wash-deep py-[11px]"
          >
            <span className="min-w-0 text-ui text-muted-4">{row.label}</span>
            {row.kind === "text" ? (
              <span
                className={`min-w-0 text-right text-ui break-words ${
                  row.tone === "accent" ? "text-accent" : "text-ink"
                }`}
              >
                {row.value}
              </span>
            ) : (
              <span className="flex items-center justify-end gap-[11px]">
                <span className="relative h-[5px] w-[78px] overflow-hidden rounded-sm bg-divider-2">
                  <span
                    style={{ width: row.width }}
                    className="absolute top-0 left-0 h-full rounded-sm bg-accent"
                  />
                </span>
                <span className="text-ui text-ink">{row.value}</span>
              </span>
            )}
          </div>
        ))}
      </div>

      {conclusion.note && (
        <div className="mt-5 flex items-start gap-[11px] rounded-lg bg-accent-tint px-3.5 py-[13px]">
          <NoteInfoIcon className="mt-px flex-none" />
          <p className="text-meta leading-[1.65] text-pretty text-accent-slate">{conclusion.note}</p>
        </div>
      )}
    </Panel>
  );
}
