import { Sidebar } from "@/components/shell/sidebar";

/**
 * The desktop frame. The comps are built for a wide viewport and scroll the
 * whole app horizontally rather than reflowing, so the main column keeps its
 * minimum width instead of collapsing.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen min-h-[620px] overflow-x-auto overflow-y-hidden bg-paper font-sans text-ink">
      <Sidebar />
      {children}
    </div>
  );
}
