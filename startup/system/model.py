"""Bedrock-backed model client.

`bedrock_model` is the one place that talks to the LLM. Every agent receives
it (or a fake) as an injected `Callable[[str, dict], dict]`; agents never
import this module directly (see shared-context.md Global Constraints).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

DEFAULT_MODEL_ID = "openai.gpt-oss-120b"


class ModelError(Exception):
    """Raised when the model reply cannot be parsed as JSON, even after a retry."""


def extract_json(text: str) -> dict:
    """Pull the first {...} JSON object out of `text`.

    Handles JSON embedded in prose and inside fenced code blocks: it looks
    for the first `{` and reads forward, tracking brace depth, until the
    braces balance, then parses that substring.
    """
    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            char = text[i]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    raise ModelError(f"no JSON object found in model reply: {text!r}")


def bedrock_model(prompt_name: str, variables: dict) -> dict:
    """Render `prompts/<prompt_name>.md` with `variables` and call the model.

    Dict/list values are JSON-dumped before substitution. Retries once on a
    JSON-parse failure, then raises ModelError. Never prints or logs the key.
    """
    load_dotenv(_REPO_ROOT / ".env")

    prompt_path = _PROMPTS_DIR / f"{prompt_name}.md"
    template = prompt_path.read_text()
    for key, value in variables.items():
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        template = template.replace("{{" + key + "}}", str(value))

    from openai import OpenAI

    client = OpenAI()
    model_id = os.getenv("MODEL_ID", DEFAULT_MODEL_ID)

    last_error: Exception | None = None
    for _ in range(2):
        response = client.chat.completions.create(
            model=model_id,
            temperature=0,
            messages=[{"role": "user", "content": template}],
        )
        reply = response.choices[0].message.content or ""
        try:
            return extract_json(reply)
        except ModelError as exc:
            last_error = exc

    raise ModelError(
        f"model reply for {prompt_name!r} did not contain valid JSON after retry: {last_error}"
    )
