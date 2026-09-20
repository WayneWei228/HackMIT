import type { Metadata } from "next";

import { getClose, getLearning } from "@/lib/api";

import { LearningScreen } from "./_components/learning-screen";

/** Every screen shows live backend state, so nothing here is prerendered at build time. */
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Learning - TrueUp",
  description:
    "How the agents learn from invoices: graded misses, replay-tested rules and the Controller's approval. All data and every upstream system is synthetic.",
};

export default async function LearningPage() {
  const [learning, close] = await Promise.all([getLearning(), getClose()]);
  return <LearningScreen learning={learning} people={close.people} />;
}
