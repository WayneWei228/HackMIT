import { AppShell } from "@/components/shell/app-shell";

/**
 * Every screen in the product sits inside the same desktop frame, so the
 * sidebar mounts once here and survives navigation between close steps.
 */
export default function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <AppShell>{children}</AppShell>;
}
