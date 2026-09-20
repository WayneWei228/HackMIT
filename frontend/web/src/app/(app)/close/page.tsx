import type { Metadata } from "next";

import { CloseCaseScreen } from "./_components/close-case-screen";

export const metadata: Metadata = {
  title: "Mintlify - December accrual | TrueUp",
  description:
    "The ingestion agent working the Mintlify December subscription accrual. All data is synthetic and every upstream system is simulated.",
};

/**
 * `/close` - the active close case.
 *
 * The screen owns two columns of the desktop frame (the case itself and the
 * live execution rail), so it is rendered as one client component rather than
 * split here; `AppShell` in the route group layout supplies the sidebar.
 */
export default function CloseCasePage() {
  return <CloseCaseScreen />;
}
