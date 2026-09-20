"""Test doubles: a throwaway workspace, a scripted Jev, a scripted LLM."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from close.workspace import CLOSE_DIR, Workspace

AS_OF = "2027-01-05T12:00:00Z"
SETTLEMENT_AS_OF = "2027-01-25T12:00:00Z"


def make_ws(tmp_path: Path, as_of: str = AS_OF, world: dict | None = None, use_real_world: bool = False) -> Workspace:
    """A Workspace under `tmp_path`, with a world dir the test fills (or the real one)."""
    world_dir = CLOSE_DIR / "world" if use_real_world else tmp_path / "world"
    ws = Workspace(
        world_dir=world_dir,
        db_dir=tmp_path / "db",
        state_dir=tmp_path / "state",
        out_dir=tmp_path / "packages",
        as_of=as_of,
    ).ensure()
    if not use_real_world:
        world_dir.mkdir(parents=True, exist_ok=True)
    for name, rows in (world or {}).items():
        write_world(ws, name, rows)
    return ws


def write_world(ws: Workspace, name: str, rows: Any) -> Path:
    """Write `world/<name>.json`; `name` may contain a slash, e.g. "documents/index"."""
    path = ws.world_dir / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2) + "\n")
    return path


def write_document(ws: Workspace, file_name: str, text: str) -> Path:
    path = ws.world_dir / "documents" / file_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


class FakeJev:
    """`answers` maps question id -> normalised answer dict, or -> callable(state) -> dict."""

    def __init__(self, answers: dict[str, Any] | None = None):
        self.answers = answers or {}
        self.calls: list[tuple] = []

    def ask(self, state: dict, questions: dict, *, tag: str) -> dict[str, dict]:
        self.calls.append((tag, state, questions))
        out = {}
        for qid in questions:
            if qid not in self.answers:
                raise KeyError(f"FakeJev has no answer scripted for {qid!r} (tag {tag!r})")
            answer = self.answers[qid]
            out[qid] = answer(state) if callable(answer) else answer
        return out


class FakeLLM:
    """`FakeLLM(extract={...}, outreach=lambda variables: {...})`."""

    def __init__(self, **by_prompt: Any):
        self.by_prompt = by_prompt
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, prompt_name: str, variables: dict) -> dict:
        self.calls.append((prompt_name, variables))
        if prompt_name not in self.by_prompt:
            raise KeyError(f"FakeLLM has no reply scripted for prompt {prompt_name!r}")
        reply = self.by_prompt[prompt_name]
        return reply(variables) if callable(reply) else reply
