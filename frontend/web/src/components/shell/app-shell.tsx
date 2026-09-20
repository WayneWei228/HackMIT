import { Sidebar, type SidebarIdentity } from "@/components/shell/sidebar";
import type { CloseView } from "@/lib/api-types";

/**
 * The desktop frame. The comps are built for a wide viewport and scroll the
 * whole app horizontally rather than reflowing, so the main column keeps its
 * minimum width instead of collapsing.
 */
export function AppShell({
  children,
  identity,
  close,
}: {
  children: React.ReactNode;
  identity?: SidebarIdentity;
  close?: CloseView | null;
}) {
  return (
    <div className="flex h-screen min-h-[620px] overflow-x-auto overflow-y-hidden bg-paper font-sans text-ink">
      <Sidebar identity={identity} close={close} />
      {children}
    </div>
  );
}
