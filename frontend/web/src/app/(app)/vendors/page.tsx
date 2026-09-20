import type { Metadata } from "next";

import { getVendors } from "@/lib/api";

import { VendorsScreen } from "./_components/vendors-screen";
import { toVendors } from "./_records";

/** Every screen shows live backend state, so nothing here is prerendered at build time. */
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Vendors - TrueUp",
  description:
    "What the agents know about each vendor. All data and every upstream system is synthetic.",
};

export default async function VendorsPage() {
  const { vendors } = await getVendors();
  return <VendorsScreen vendors={toVendors(vendors)} />;
}
