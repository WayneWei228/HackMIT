import { AppShell } from "@/components/shell/app-shell";
import { AppProviders } from "@/components/shell/providers";
import type { SidebarIdentity } from "@/components/shell/sidebar";
import { getClose } from "@/lib/api";

/** Every screen shows live backend state, so nothing here is prerendered at build time. */
export const dynamic = "force-dynamic";

/** The user the app acts for is the configured Controller; without a backend the sidebar says so. */
async function identity(): Promise<SidebarIdentity | undefined> {
  try {
    const close = await getClose();
    return {
      periodLabel: close.period_label,
      controllerName: close.controller_name,
      controllerRole: close.people.find((p) => p.person_id === close.controller_id)?.role ?? "Controller",
    };
  } catch {
    return undefined;
  }
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
  return (
    <AppProviders>
      <AppShell identity={await identity()}>{children}</AppShell>
    </AppProviders>
  );
}
