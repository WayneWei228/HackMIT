import type { Metadata } from "next";
import { Newsreader } from "next/font/google";

import { MotionProvider } from "@/components/shell/motion-provider";
import "./globals.css";

/*
 * The comps load Newsreader as a variable font across both axes
 * (`opsz,wght@6..72,300;6..72,400;6..72,500`). Pinning `weight` here would
 * fetch static instances instead, which set every display run 1-4% wide and
 * lose the optical-size axis that `font-optical-sizing: auto` relies on.
 */
const newsreader = Newsreader({
  subsets: ["latin"],
  axes: ["opsz"],
  style: ["normal", "italic"],
  display: "swap",
  variable: "--font-newsreader",
});

export const metadata: Metadata = {
  title: "TrueUp",
  description:
    "Month-end service accrual, closed by an agent and graded by the invoice. All data shown and every system behind it is synthetic.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={newsreader.variable}>
      <body className="bg-paper text-ink antialiased">
        <MotionProvider>{children}</MotionProvider>
      </body>
    </html>
  );
}
