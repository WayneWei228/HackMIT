"use client";

import Link from "next/link";

import type { VendorStory } from "../../_handoff/types";
import { storyHref } from "./story-href";

/**
 * Whose story to read. Every vendor is counted at the same cut as the page,
 * so the panel is the month at a glance: who has had anything happen yet, and
 * who is still owed an answer.
 */
export function VendorPanel({ story }: { story: VendorStory }) {
  return (
    <nav
      aria-label="Vendors"
      className="w-[232px] flex-none overflow-y-auto border-r border-line bg-rail px-3 pt-5 pb-6"
    >
      <div className="px-2.5 pb-2 text-meta text-faint-2">Vendors</div>
      {story.vendors.map((vendor) => {
        const active = vendor.vendor_id === story.vendor_id;
        const quiet = vendor.events === 0;
        return (
          <Link
            key={vendor.vendor_id}
            href={storyHref(vendor.vendor_id, story.through)}
            aria-current={active ? "page" : undefined}
            className={`block rounded-lg border px-2.5 py-2 transition-colors duration-[160ms] ${
              active
                ? "border-line bg-panel"
                : "border-transparent hover:bg-hover"
            }`}
          >
            <div
              className={`text-body ${
                active ? "font-medium text-ink" : quiet ? "text-faint-2" : "text-ink-2"
              }`}
            >
              {vendor.vendor_name}
            </div>
            <div className="mt-0.5 text-tiny text-faint-2">
              {quiet
                ? "nothing yet"
                : `${vendor.events} ${vendor.events === 1 ? "event" : "events"}`}
              {vendor.open_questions > 0 && (
                <span className="ml-1.5 text-accent-dark">
                  {vendor.open_questions === 1
                    ? "1 question out"
                    : `${vendor.open_questions} questions out`}
                </span>
              )}
            </div>
          </Link>
        );
      })}
    </nav>
  );
}
