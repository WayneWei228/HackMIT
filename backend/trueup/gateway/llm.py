"""The only module allowed to call a language model.

Uses the OpenAI SDK against either of two backends:
- OpenAI directly: set OPENAI_API_KEY (and OPENAI_BASE_URL for compatible endpoints).
- OpenAI models on AWS Bedrock: set AWS_BEARER_TOKEN_BEDROCK (and AWS_REGION, default
  us-east-2). Used only when OPENAI_API_KEY is not set.
Set MODEL_ID to pick the model. Engines call complete/complete_json for extraction,
narration, and diagnosis, never a model directly.
"""

from __future__ import annotations

import json
import os
import re

from pydantic import BaseModel, ValidationError

from trueup.gateway import tracing

DEFAULT_MODEL = "gpt-5"
BEDROCK_DEFAULT_MODEL = "openai.gpt-oss-120b-1:0"
BEDROCK_DEFAULT_REGION = "us-east-2"
JSON_ATTEMPTS = 2
# gpt-oss models on Bedrock return their chain of thought inline before the answer.
_REASONING = re.compile(r"<reasoning>.*?</reasoning>", re.DOTALL)


class LLMError(Exception):
    """Raised when the model call fails or returns unusable output."""


def _use_bedrock() -> bool:
    return not os.environ.get("OPENAI_API_KEY") and bool(os.environ.get("AWS_BEARER_TOKEN_BEDROCK"))


def available() -> bool:
    """True when credentials are configured, so callers can skip live model steps."""
    return bool(os.environ.get("OPENAI_API_KEY")) or _use_bedrock()


@tracing.span("CHAIN", name="llm.complete")
def complete(prompt: str, system: str | None = None, model: str | None = None) -> str:
    """Return the model's text completion for the prompt."""
    default = BEDROCK_DEFAULT_MODEL if _use_bedrock() else DEFAULT_MODEL
    model = model or os.environ.get("MODEL_ID") or default
    messages = [{"role": "user", "content": prompt}]
    if system is not None:
        messages.insert(0, {"role": "system", "content": system})
    try:
        response = _client().chat.completions.create(model=model, messages=messages)
    except Exception as exc:
        raise LLMError(f"OpenAI call failed: {exc}") from exc
    text = response.choices[0].message.content if response.choices else None
    text = _REASONING.sub("", text or "").strip()
    if not text:
        raise LLMError("OpenAI returned no text content")
    return text


@tracing.span("CHAIN", name="llm.complete_json")
def complete_json(
    prompt: str,
    schema: type[BaseModel],
    system: str | None = None,
    model: str | None = None,
) -> BaseModel:
    """Return a validated instance of `schema` parsed from the model's output.

    Retries once when the reply is not valid JSON for the schema.
    """
    json_schema = json.dumps(schema.model_json_schema())
    wrapped = (
        f"{prompt}\n\n"
        "Respond with a single JSON object matching this JSON schema, "
        f"with no surrounding text or code fences:\n{json_schema}"
    )
    last_error: Exception | None = None
    for _ in range(JSON_ATTEMPTS):
        raw = complete(wrapped, system=system, model=model)
        try:
            return schema.model_validate_json(_extract_json_object(raw))
        except (ValidationError, ValueError) as exc:
            last_error = exc
    raise LLMError(f"model output did not match {schema.__name__}: {last_error}") from last_error


def _client():
    from openai import OpenAI

    if _use_bedrock():
        region = os.environ.get("AWS_REGION", BEDROCK_DEFAULT_REGION)
        return OpenAI(
            api_key=os.environ["AWS_BEARER_TOKEN_BEDROCK"],
            base_url=f"https://bedrock-runtime.{region}.amazonaws.com/openai/v1",
        )
    return OpenAI()


def _extract_json_object(text: str) -> str:
    """Return the first balanced {...} object in `text`, ignoring prose and code fences."""
    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escaped = False
        for i in range(start, len(text)):
            char = text[i]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
            elif char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    try:
                        json.loads(candidate)
                    except json.JSONDecodeError:
                        break
                    return candidate
        start = text.find("{", start + 1)
    raise ValueError(f"no JSON object found in model reply: {text[:200]!r}")
