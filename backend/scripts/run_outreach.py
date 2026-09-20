"""Run the outreach flow for OpenAI and ASUS: python scripts/run_outreach.py.

OpenAI has partial December usage at close, so it asks for the total and, after the reply, is
re-estimated and permitted. ASUS goes to the Controller under policy; a stand-in for the
Controller's request then asks for the in-service date and the reply is not enough.
A language model drafts and reads the messages when one is configured; otherwise the template
and the offline reader are used.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trueup.agents.classification_agent import classify  # noqa: E402
from trueup.agents.estimation_agent import estimate  # noqa: E402
from trueup.agents.outreach_agent import Topic, poll_replies, send_outreach  # noqa: E402
from trueup.agents.policy_agent import enforce  # noqa: E402
from trueup.simulator.simulator import Simulator  # noqa: E402
from trueup.simulator.stand_in import open_obligation_for_classification  # noqa: E402
from trueup.store import enums as e  # noqa: E402
from trueup.store.workflow import advance  # noqa: E402

PERIOD = "2026-12"
CLOSE = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)
OPENAI_REPLY_AT = "2027-01-02T10:00:00Z"
ASUS_REPLY_AT = "2027-01-04T10:00:00Z"
ESTIMATE = (e.WorkflowStage.ESTIMATING, e.NextAction.ESTIMATE)
CONTROLLER_STATE = "AWAITING_CONTROLLER/CONTROLLER_REVIEW"


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def state(obligation) -> str:
    return f"{obligation.workflow_stage.value}/{obligation.next_action.value}"


def main() -> None:
    sim = Simulator.initialize()
    sim.advance_to(CLOSE)
    checks: list[tuple[str, bool]] = []

    def expect(label: str, ok: bool) -> None:
        checks.append((label, ok))

    with sim.session() as session:

        def responder(key: str, now: datetime) -> str | None:
            return sim.reply_to_outreach(key, session)

        print("== At close (2026-12-31) ==")
        openai = open_obligation_for_classification(session, "VEN-OPENAI", PERIOD, now=CLOSE)
        classify(session, openai.obligation_id, now=CLOSE)
        first = estimate(session, openai.obligation_id, now=CLOSE)
        print(f"OpenAI  estimate: {first.outcome}, evidence {first.evidence_status.value}")
        expect(
            "OpenAI has no estimate at close and needs usage",
            first.outcome == "NEEDS_OUTREACH"
            and first.evidence_status == e.EvidenceStatus.MISSING_USAGE,
        )

        asus = open_obligation_for_classification(session, "VEN-ASUS", PERIOD, now=CLOSE)
        classify(session, asus.obligation_id, now=CLOSE)
        estimate(session, asus.obligation_id, now=CLOSE)
        gate = enforce(session, asus.obligation_id, now=CLOSE)
        print(f"ASUS    policy: {gate.decision.value} -> {state(asus)}")
        expect(
            "ASUS goes to the Controller under policy",
            gate.decision == e.PolicyDecision.REQUIRE_CONTROLLER
            and state(asus) == CONTROLLER_STATE,
        )

        print("\n== Sending ==")
        request = send_outreach(session, openai.obligation_id, now=CLOSE)
        print(f"OpenAI  to {request.recipient_person_id} ({request.drafted_by}): {request.subject}")
        print("\n".join(f"        | {line}" for line in request.body.splitlines()))
        expect(
            "OpenAI outreach asks the service owner for usage",
            request.topic == Topic.USAGE_CONFIRMATION and request.recipient_person_id == "ENG-001",
        )
        advance(
            asus,
            e.WorkflowStage.AWAITING_OUTREACH,
            e.NextAction.SEND_OUTREACH,
            "controller-stand-in",
            at=CLOSE,
        )
        asus_request = send_outreach(
            session, asus.obligation_id, now=CLOSE, topic=Topic.IN_SERVICE_DATE
        )
        who = f"{asus_request.recipient_person_id} ({asus_request.drafted_by})"
        print(f"ASUS    to {who}: {asus_request.subject}")
        expect(
            "ASUS outreach asks the service owner for the in-service date",
            asus_request.topic == Topic.IN_SERVICE_DATE
            and asus_request.recipient_person_id == "OPS-001",
        )

        print("\n== 2027-01-02: the OpenAI reply arrives ==")
        sim.advance_to(OPENAI_REPLY_AT)
        now = aware(sim.now())
        (reply,) = poll_replies(session, now=now, responder=responder)
        print(
            f"OpenAI  reply read by {reply.parsed_by}: resolved={reply.resolved} "
            f"quantity={reply.quantity} {reply.unit} -> "
            f"{reply.routed_stage.value}/{reply.next_action.value}"
        )
        expect(
            "OpenAI reply gives 930000 API_CALL and returns to Estimation",
            reply.resolved
            and reply.quantity == Decimal("930000")
            and reply.unit == "API_CALL"
            and (reply.routed_stage, reply.next_action) == ESTIMATE,
        )
        second = estimate(session, openai.obligation_id, now=now)
        print(f"OpenAI  re-estimate: {second.amount} ({second.expression})")
        verdict = enforce(session, openai.obligation_id, now=now)
        print(f"OpenAI  policy: {verdict.decision.value} -> {state(openai)}")
        expect("OpenAI re-estimates at 18600.00", second.amount == Decimal("18600.00"))
        expect("OpenAI is permitted by policy", verdict.decision == e.PolicyDecision.PERMIT)

        print("\n== 2027-01-04: the ASUS reply arrives ==")
        sim.advance_to(ASUS_REPLY_AT)
        now = aware(sim.now())
        (asus_reply,) = poll_replies(session, now=now, responder=responder)
        print(
            f"ASUS    reply read by {asus_reply.parsed_by}: resolved={asus_reply.resolved} "
            f"-> {asus_reply.routed_stage.value}/{asus_reply.next_action.value}"
        )
        for note in asus_reply.uncertainties:
            print(f"        note: {note}")
        expect(
            "ASUS reply is not enough and goes back to the Controller",
            not asus_reply.resolved and state(asus) == CONTROLLER_STATE,
        )

    print("\n== EXPECTED ==")
    for label, ok in checks:
        print(f"[{'hit' if ok else 'MISS'}] {label}")
    hits = sum(ok for _, ok in checks)
    print(f"{hits}/{len(checks)} expected outcomes matched")
    if hits != len(checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
