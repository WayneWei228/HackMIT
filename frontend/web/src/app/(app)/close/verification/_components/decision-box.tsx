"use client";

import { useState } from "react";

import { Button } from "@/components/ui/primitives";
import { decideObligation } from "@/lib/api";
import type { Decision } from "@/lib/api-types";
import { useApiAction } from "@/lib/use-api-action";

import { useVerificationScreen } from "./screen-context";

const FIELD =
  "w-full rounded-lg border border-line-warm bg-panel-hover px-[11px] py-[7px] text-sm leading-[1.4] text-ink outline-none focus-visible:shadow-[var(--shadow-ring-soft)]";

/**
 * The Controller's three moves on a case that is waiting for them. The buttons
 * only offer what the backend allows, and a disabled Approve says why in words.
 */
export function DecisionBox() {
  const { controller, controllerId, people, obligationId } = useVerificationScreen();
  const { run, pending, error } = useApiAction();
  const [notes, setNotes] = useState("");
  const [actor, setActor] = useState(controllerId);
  const allowed = new Set(controller.allowed_decisions);
  const canApprove = allowed.has("APPROVE");
  const canRequest = allowed.has("REQUEST_MORE_EVIDENCE");
  const canReject = allowed.has("REJECT");
  const whyNoApprove = controller.blocked
    ? `Policy blocked this accrual, so it cannot be approved. ${controller.reason}`.trim()
    : `Approve is not offered for this case. ${controller.reason}`.trim();

  const decide = (decision: Decision) =>
    run(() => decideObligation(obligationId, { decision, notes, decided_by: actor }));

  return (
    <div className="mt-[18px] flex flex-col gap-2">
      <div className="text-eyebrow font-medium tracking-caps-lg text-faint">CONTROLLER DECISION</div>
      <label className="mt-1 text-meta text-muted-4" htmlFor="acting-as">
        Acting as
      </label>
      <select
        id="acting-as"
        value={actor}
        onChange={(event) => setActor(event.target.value)}
        className={FIELD}
      >
        {people.map((person) => (
          <option key={person.person_id} value={person.person_id}>
            {person.name} ({person.role})
          </option>
        ))}
      </select>
      <label className="mt-1 text-meta text-muted-4" htmlFor="decision-notes">
        Notes
      </label>
      <textarea
        id="decision-notes"
        value={notes}
        onChange={(event) => setNotes(event.target.value)}
        rows={2}
        placeholder="Why this decision"
        className={`${FIELD} resize-none`}
      />
      {/* text-[13.5px]: `cn` reads the custom `text-ui` token as a colour and drops it against
          the variant's own text colour, so the size and line-height are restated here. */}
      <Button
        variant="solid"
        disabled={!canApprove || pending}
        title={canApprove ? undefined : whyNoApprove}
        onClick={() => decide("APPROVE")}
        className="mt-1 w-full justify-center border border-accent px-3.5 text-[13.5px] leading-none hover:bg-accent-deep disabled:cursor-not-allowed disabled:opacity-45"
      >
        Approve and post journal
      </Button>
      {!canApprove && (
        <div className="text-meta leading-[1.5] text-muted-4" role="note">
          {whyNoApprove}
        </div>
      )}
      <Button
        variant="secondary"
        disabled={!canRequest || pending}
        onClick={() => decide("REQUEST_MORE_EVIDENCE")}
        className="w-full justify-center px-3.5 text-[13.5px] leading-none"
      >
        Request more evidence
      </Button>
      <Button
        variant="secondary"
        disabled={!canReject || pending}
        onClick={() => decide("REJECT")}
        className="w-full justify-center px-3.5 text-[13.5px] leading-none"
      >
        Reject
      </Button>
      {error && <div className="text-meta leading-[1.5] text-[#A4452F]">{error}</div>}
    </div>
  );
}
