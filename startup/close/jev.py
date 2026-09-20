"""Jev: typed judgments over case state. Questions in, normalised dicts out."""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Protocol

from typesafe_sdk import Choice, Noul, Score, TypeSafeClient, TypeSafeError
from typesafe_sdk.constants import API_KEY_ENV

from close.workspace import Workspace, load_env

MODEL = "jev-latest"
CALL_LOG = "jev_calls.jsonl"

Question = Choice | Noul | Score


class Jev(Protocol):
    def ask(self, state: dict, questions: dict[str, Question], *, tag: str) -> dict[str, dict]: ...


class JevUnavailable(Exception):
    """No answer from Jev. Callers gate the case to REVIEW; they never guess."""


def _criteria(question: Any) -> Any:
    if isinstance(question, dict):
        return question.get("criteria")
    return getattr(question, "criteria", None)


def normalise(answer: Any, question: Any) -> dict:
    """Turn an SDK answer object into the plain JSON-serialisable dict workers consume."""
    kind = getattr(answer, "type", None)
    if kind == "noul":
        return {"type": "noul", "noul": float(answer.noul)}
    if kind == "choice":
        return {
            "type": "choice",
            "choice": answer.choice,
            "confidence": float(answer.confidence),
            "probabilities": {str(k): float(v) for k, v in answer.probabilities.items()},
        }
    if kind == "score":
        levels = _criteria(question) or []
        span = max(len(levels) - 1, 1)
        return {
            "type": "score",
            "score": float(answer.score) / span,
            "confidence": float(answer.confidence),
            "probabilities": {str(k): float(v) for k, v in answer.probabilities.items()},
        }
    raise JevUnavailable(f"unknown answer type {kind!r}")


def dump_questions(questions: dict[str, Question]) -> dict:
    """Questions as plain dicts, for the call log."""
    out = {}
    for qid, q in questions.items():
        out[qid] = dict(q) if isinstance(q, dict) else q.model_dump()
    return out


def state_hash(state: Any) -> str:
    return hashlib.sha256(json.dumps(state, sort_keys=True, default=str).encode()).hexdigest()


class TypeSafeJev:
    """The real client. One system_one call per ask(); every call is logged."""

    def __init__(self, ws: Workspace, client: Any = None):
        self.ws = ws
        self._client = client

    def client(self) -> Any:
        if self._client is None:
            load_env()
            if not os.environ.get(API_KEY_ENV, "").strip():
                raise JevUnavailable(f"{API_KEY_ENV} is not set")
            try:
                self._client = TypeSafeClient(model=MODEL)
            except TypeSafeError as exc:
                raise JevUnavailable(str(exc)) from exc
        return self._client

    def ask(self, state: dict, questions: dict[str, Question], *, tag: str) -> dict[str, dict]:
        client = self.client()
        started = time.time()
        try:
            response = client.system_one(state=state, questions=questions)
        except TypeSafeError as exc:
            self._log(tag, state, questions, {}, started, error=f"{type(exc).__name__}: {exc}")
            raise JevUnavailable(str(exc)) from exc
        answers = {qid: normalise(response.answers[qid], questions[qid]) for qid in questions}
        self._log(tag, state, questions, answers, started)
        return answers

    def _log(self, tag, state, questions, answers, started, error=None) -> None:
        entry = {
            "at": self.ws.as_of,
            "tag": tag,
            "state_hash": state_hash(state),
            "questions": dump_questions(questions),
            "answers": answers,
            "ms": int((time.time() - started) * 1000),
        }
        if error:
            entry["error"] = error
        path = self.ws.state_dir / CALL_LOG
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as fh:
            fh.write(json.dumps(entry, default=str) + "\n")


def read_calls(ws: Workspace) -> list[dict]:
    path = ws.state_dir / CALL_LOG
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
