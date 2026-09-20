import type { Metadata } from "next";

import { ObligationRoute } from "./_components/obligation-route";

export const metadata: Metadata = {
  title: "Obligation - TrueUp",
  description:
    "The obligation agent deciding what is owed for the period. All data is synthetic and every upstream system is simulated.",
};

/** The screen draws from the browser's copy of the case and its agent starts by itself when it opens. */
export default function Page() {
  return <ObligationRoute />;
}
