import { CloseControls } from "@/components/close/close-controls";
import type { CloseView } from "@/lib/api-types";

/** What a close screen shows before the December close has opened any obligation. */
export function NoCases({ close }: { close: CloseView }) {
  return (
    <main className="flex min-w-[760px] flex-1 flex-col items-center justify-center gap-3 px-10">
      <div className="text-eyebrow font-medium tracking-caps-xl text-faint-2">
        {close.period_label.toUpperCase()}
      </div>
      <div className="font-display text-4xl text-ink-deep">No cases are open yet</div>
      <p className="max-w-[440px] text-center text-lead text-muted-4 text-pretty">
        The close has not started. Running it opens one obligation per vendor and hands each to the
        agents.
      </p>
      <div className="mt-2">
        <CloseControls close={close} />
      </div>
    </main>
  );
}
