import type { Metadata } from "next";

import { IngestionRoute } from "./_components/ingestion-route";

export const metadata: Metadata = {
  title: "Active case - TrueUp",
  description:
    "The ingestion agent choosing which files matter for a vendor's month-end accrual. All data is synthetic and every upstream system is simulated.",
};

/** The screen draws from the browser's copy of the case and its agent starts by itself when it opens. */
export default function Page() {
  return <IngestionRoute />;
}
