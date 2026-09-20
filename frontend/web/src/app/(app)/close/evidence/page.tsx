import type { Metadata } from "next";

import { EvidenceRoute } from "./_components/evidence-route";

export const metadata: Metadata = {
  title: "Evidence - TrueUp",
  description:
    "The evidence agent reading the documents ingestion kept. All data is synthetic and every upstream system is simulated.",
};

/** The screen draws from the browser's copy of the case and its agent starts by itself when it opens. */
export default function Page() {
  return <EvidenceRoute />;
}
