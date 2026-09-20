"""The LLM: document text and message drafts in, parsed JSON out. It never decides anything."""

from __future__ import annotations

import json
import os
import re
import urllib.request

from close.workspace import CLOSE_DIR, load_env

PROMPTS_DIR = CLOSE_DIR / "prompts"
DEFAULT_MODEL = "us.anthropic.claude-opus-4-6-v1"


class LLMError(Exception):
    """The model did not return usable JSON."""


def render(prompt_name: str, variables: dict) -> str:
    path = PROMPTS_DIR / f"{prompt_name}.md"
    if not path.exists():
        raise LLMError(f"no prompt {prompt_name!r} at {path}")
    text = path.read_text()
    for key, value in variables.items():
        rendered = value if isinstance(value, str) else json.dumps(value, indent=2, default=str)
        text = text.replace("{{" + key + "}}", rendered)
    return text


def extract_json(text: str) -> dict:
    """The first balanced JSON object in the reply, ignoring prose and code fences."""
    start = text.find("{")
    while start != -1:
        depth, in_string, escaped = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    raise LLMError("no JSON object in reply")


def _converse(model: str, prompt: str, api_key: str) -> str:
    """Anthropic models are not on the OpenAI-compatible endpoint; they go through Bedrock's native Converse API."""
    base = os.environ.get("BEDROCK_RUNTIME_URL")
    if not base:
        region = re.search(r"[a-z]{2}-[a-z]+-\d", os.environ.get("OPENAI_BASE_URL", ""))
        base = f"https://bedrock-runtime.{region.group(0) if region else 'us-east-2'}.amazonaws.com"
    body = {"messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": {"temperature": 0, "maxTokens": 4096}}
    request = urllib.request.Request(
        f"{base}/model/{model}/converse", data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=120) as reply:
        blocks = json.load(reply)["output"]["message"]["content"]
    return "".join(b.get("text", "") for b in blocks)


def _chat(model: str, prompt: str, api_key: str) -> str:
    from openai import OpenAI

    client = OpenAI(base_url=os.environ.get("OPENAI_BASE_URL"), api_key=api_key)
    reply = client.chat.completions.create(model=model, temperature=0, messages=[{"role": "user", "content": prompt}])
    return reply.choices[0].message.content or ""


def bedrock_llm(prompt_name: str, variables: dict) -> dict:
    """Render `prompts/<prompt_name>.md`, call the model at temperature 0, parse its JSON."""
    load_env()
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise LLMError("OPENAI_API_KEY is not set")
    model = os.environ.get("MODEL_ID", DEFAULT_MODEL)
    call = _converse if "anthropic." in model else _chat
    prompt = render(prompt_name, variables)
    last: Exception | None = None
    for _ in range(2):
        try:
            return extract_json(call(model, prompt, api_key))
        except Exception as exc:  # noqa: BLE001 - one retry, then surface as LLMError
            last = exc
    raise LLMError(f"{prompt_name}: {last}") from last
