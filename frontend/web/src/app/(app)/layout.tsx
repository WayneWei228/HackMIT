import { AppShell } from "@/components/shell/app-shell";
import { AppProviders } from "@/components/shell/providers";
import type { SidebarIdentity } from "@/components/shell/sidebar";
import { getClose, getPeriods } from "@/lib/api";
import type { CloseView } from "@/lib/api-types";
import type { PeriodsView } from "@/lib/report-types";

/** Every screen shows live backend state, so nothing here is prerendered at build time. */
export const dynamic = "force-dynamic";

type Shell = { close: CloseView; calendar: PeriodsView };

/** The close and its calendar, or null when the backend is not reachable, so the sidebar can say so. */
async function readShell(): Promise<Shell | null> {
  try {
    const [close, calendar] = await Promise.all([getClose(), getPeriods()]);
    return { close, calendar };
  } catch {
    return null;
  }
}

/** The user the app acts for is the configured Controller; without a backend the sidebar says so. */
function identityOf(shell: Shell | null): SidebarIdentity | undefined {
  if (!shell) return undefined;
  const { close, calendar } = shell;
  return {
    periodLabel: close.period_label,
    controllerName: close.controller_name,
    controllerRole: close.people.find((p) => p.person_id === close.controller_id)?.role ?? "Controller",
    calendar,
  };
}

/**
 * Every screen in the product sits inside the same desktop frame, so the
 * sidebar mounts once here and survives navigation between close steps.
 */
export default async function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const shell = await readShell();
  return (
    <AppProviders>
      <AppShell identity={identityOf(shell)} close={shell?.close ?? null}>
        {children}
      </AppShell>
    </AppProviders>
  );
}
