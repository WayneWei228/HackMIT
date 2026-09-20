import { AppShell } from "@/components/shell/app-shell";
import { AppProviders } from "@/components/shell/providers";
import type { SidebarIdentity } from "@/components/shell/sidebar";
import { getClose } from "@/lib/api";
import type { CloseView } from "@/lib/api-types";

/** Every screen shows live backend state, so nothing here is prerendered at build time. */
export const dynamic = "force-dynamic";

/** The close, or null when the backend is not reachable, so the sidebar can say so. */
async function readClose(): Promise<CloseView | null> {
  try {
    return await getClose();
  } catch {
    return null;
  }
}

/** The user the app acts for is the configured Controller; without a backend the sidebar says so. */
function identityOf(close: CloseView | null): SidebarIdentity | undefined {
  if (!close) return undefined;
  return {
    periodLabel: close.period_label,
    controllerName: close.controller_name,
    controllerRole: close.people.find((p) => p.person_id === close.controller_id)?.role ?? "Controller",
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
  const close = await readClose();
  return (
    <AppProviders>
      <AppShell identity={identityOf(close)} close={close}>
        {children}
      </AppShell>
    </AppProviders>
  );
}
