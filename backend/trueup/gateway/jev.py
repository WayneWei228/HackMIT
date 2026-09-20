"""The only module allowed to call Jev (TypeSafe System One).

Jev takes a state and typed questions and returns a choice with calibrated
probabilities. It generates no text and calls no tools, so it is used only for
fast classification. Callers must handle JevError and fall back to rules.
"""

from __future__ import annotations

import os

from pydantic import BaseModel

from trueup.gateway import tracing


class JevError(Exception):
    """Raised when Jev is unavailable or returns unusable output."""


class JevAnswer(BaseModel):
    choice: str
    confidence: float
    probabilities: dict[str, float]


# A question is (instructions, {label: optional description}).
Question = tuple[str, dict[str, str | None]]


def available() -> bool:
    return bool(os.environ.get("TYPESAFE_API_KEY"))


@tracing.span("TOOL", name="jev.classify")
def classify(state: dict, questions: dict[str, Question]) -> dict[str, JevAnswer]:
    """Ask Jev one or more Choice questions about `state` in a single request."""
    if not available():
        raise JevError("TYPESAFE_API_KEY is not set")
    try:
        from typesafe_sdk import Choice, TypeSafeClient

        wire = {
            name: Choice(instructions=instructions, criteria=criteria)
            for name, (instructions, criteria) in questions.items()
        }
        with TypeSafeClient() as client:
            response = client.system_one(state=state, questions=wire)
        return {
            name: JevAnswer(
                choice=answer.choice,
                confidence=answer.confidence,
                probabilities=dict(answer.probabilities),
            )
            for name, answer in response.choices.items()
        }
    except Exception as exc:
        raise JevError(f"Jev call failed: {exc}") from exc
