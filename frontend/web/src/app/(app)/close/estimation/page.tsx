import type { Metadata } from "next";

import { EstimationRoute } from "./_components/estimation-route";

export const metadata: Metadata = {
  title: "Estimation - TrueUp",
  description:
    "The estimation agent building the accrual amount. All data and every upstream system is synthetic.",
};

/** The screen draws from the browser's copy of the case and its agent starts by itself when it opens. */
export default function Page() {
  return <EstimationRoute />;
}
