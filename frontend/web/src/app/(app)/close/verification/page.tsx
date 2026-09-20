import type { Metadata } from "next";

import { VerificationRoute } from "./_components/verification-route";

export const metadata: Metadata = {
  title: "Verification - TrueUp",
  description:
    "The policy checks and the Controller's decision on an accrual. All data is synthetic and every upstream system is simulated.",
};

/** The screen draws from the browser's copy of the case and its agent starts by itself when it opens. */
export default function Page() {
  return <VerificationRoute />;
}
