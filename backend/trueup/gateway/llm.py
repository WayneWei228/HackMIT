"""The only module allowed to call a language model.

Uses the OpenAI SDK against either of two backends:
- OpenAI directly: set OPENAI_API_KEY (and OPENAI_BASE_URL for compatible endpoints).
- OpenAI models on AWS Bedrock: set AWS_BEARER_TOKEN_BEDROCK. The region is AWS_REGION when set,
  otherwise the one the key is signed for, otherwise us-east-2. Used only when OPENAI_API_KEY is
  not set.
Set MODEL_ID to pick the model. Engines call complete/complete_json for extraction,
narration, and diagnosis, never a model directly.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import os
import re
import time
import urllib.parse
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from trueup.gateway import tracing

DEFAULT_MODEL = "gpt-5"
BEDROCK_DEFAULT_MODEL = "openai.gpt-oss-120b-1:0"
BEDROCK_DEFAULT_REGION = "us-east-2"
JSON_ATTEMPTS = 2
CALL_ATTEMPTS = 3
REQUEST_TIMEOUT_SECONDS = 60.0
BACKOFF_SECONDS = (1.0, 3.0)
_TRANSIENT_STATUS = frozenset({408, 409, 429})
_sleep = time.sleep
# gpt-oss models on Bedrock return their chain of thought inline before the answer.
_REASONING = re.compile(r"<reasoning>.*?</reasoning>", re.DOTALL)


class LLMError(Exception):
    """Raised when the model call fails or returns unusable output."""


class LLMAuthError(LLMError):
    """The provider rejected the credentials (401 or 403). Retrying cannot help."""


_AUTH_STATUS = frozenset({401, 403})
_KEY_PREFIX = "bedrock-api-key-"
_REGION = re.compile(r"^[a-z]{2}(?:-[a-z]+)+-\d$")
_health: dict[str, str | None] = {"status": "unknown", "last_error": None, "last_ok_at": None}
PROBE_PROMPT = "Reply with the single word: ok"


@dataclass(frozen=True)
class KeyInfo:
    """What a Bedrock API key says about itself, read from the key and never from the network."""

    region: str | None
    expires_at: str | None


def key_info(key: str) -> KeyInfo:
    """The region a Bedrock key is signed for and the latest moment it can still work.

    A key is a base64 presigned URL. Its credential scope names the region, and its date plus
    lifetime give an upper bound on expiry: the session token inside can lapse earlier.
    """
    encoded = key.strip().removeprefix(_KEY_PREFIX)
    try:
        decoded = base64.b64decode(encoded + "=" * (-len(encoded) % 4)).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return KeyInfo(None, None)
    query = urllib.parse.parse_qs(decoded.partition("?")[2])
    scope = query.get("X-Amz-Credential", [""])[0].split("/")
    region = scope[2] if len(scope) >= 5 and scope[3] == "bedrock" else None
    if region is not None and not _REGION.match(region):
        region = None
    expires_at = None
    try:
        signed = dt.datetime.strptime(query["X-Amz-Date"][0], "%Y%m%dT%H%M%SZ")
        lifetime = dt.timedelta(seconds=int(query["X-Amz-Expires"][0]))
        expires_at = (signed + lifetime).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (KeyError, ValueError, IndexError):
        pass
    return KeyInfo(region, expires_at)


def _region() -> str:
    """AWS_REGION when set, else the region the key is signed for, else the default."""
    configured = os.environ.get("AWS_REGION")
    if configured:
        return configured
    signed_for = key_info(os.environ.get("AWS_BEARER_TOKEN_BEDROCK", "")).region
    return signed_for or BEDROCK_DEFAULT_REGION


def health() -> dict[str, str | None]:
    """What the last live call in this process said, with no extra model call.

    mode is "live" when credentials are configured and "offline" otherwise. status is "unknown"
    until a call has been made, then "ok", "credentials_rejected" (401 or 403) or "unavailable".
    expires_at is the latest a Bedrock key can still work, or None when the key does not say.
    """
    mode = "live" if available() else "offline"
    expires_at = None
    if _use_bedrock():
        expires_at = key_info(os.environ.get("AWS_BEARER_TOKEN_BEDROCK", "")).expires_at
    return {"mode": mode, **_health, "expires_at": expires_at}


def probe() -> dict[str, str | None]:
    """One tiny live call, so the health above reflects the model now and not the last case run."""
    if available():
        try:
            complete(PROBE_PROMPT)
        except LLMError:
            pass
    return health()


def _record_ok() -> None:
    _health.update(
        status="ok", last_error=None, last_ok_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    )


def _record_failure(error: LLMError) -> None:
    status = "credentials_rejected" if isinstance(error, LLMAuthError) else "unavailable"
    _health.update(status=status, last_error=str(error)[:300])


def _use_bedrock() -> bool:
    return not os.environ.get("OPENAI_API_KEY") and bool(os.environ.get("AWS_BEARER_TOKEN_BEDROCK"))


def available() -> bool:
    """True when credentials are configured, so callers can skip live model steps."""
    return bool(os.environ.get("OPENAI_API_KEY")) or _use_bedrock()


def _status_of(exc: Exception) -> int | None:
    status = getattr(exc, "status_code", None)
    return status if isinstance(status, int) else None


def _is_transient(exc: Exception) -> bool:
    """A throttle, a server error, a timeout or a dropped connection: worth another try."""
    status = _status_of(exc)
    if status is not None:
        return status in _TRANSIENT_STATUS or status >= 500
    return isinstance(exc, TimeoutError | ConnectionError) or type(exc).__name__ in {
        "APIConnectionError",
        "APITimeoutError",
    }


def _auth_message(status: int | None) -> str:
    text = f"Model credentials were rejected ({status}); refresh the Bedrock token."
    if _use_bedrock():
        info = key_info(os.environ.get("AWS_BEARER_TOKEN_BEDROCK", ""))
        region = _region()
        if info.expires_at and info.expires_at < dt.datetime.now(dt.UTC).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ):
            text += f" The key expired at {info.expires_at}."
        elif info.region and info.region != region:
            text += f" The key is signed for {info.region} but the call went to {region}."
        else:
            text += (
                f" A 401 can also mean the key was signed for a different region than {region},"
                " or that its session lapsed before its stated expiry."
            )
    return text


def _describe(exc: Exception) -> str:
    status = _status_of(exc)
    kind = type(exc).__name__ + (f" {status}" if status is not None else "")
    return f"{kind}: {str(exc)[:300]}"


@tracing.span("CHAIN", name="llm.complete")
def complete(prompt: str, system: str | None = None, model: str | None = None) -> str:
    """Return the model's text completion for the prompt.

    A throttle, a server error, a timeout or a dropped connection is retried a few times with a
    short pause; anything else, and the last failure, raises `LLMError` naming what went wrong.
    """
    default = BEDROCK_DEFAULT_MODEL if _use_bedrock() else DEFAULT_MODEL
    model = model or os.environ.get("MODEL_ID") or default
    messages = [{"role": "user", "content": prompt}]
    if system is not None:
        messages.insert(0, {"role": "system", "content": system})
    for attempt in range(1, CALL_ATTEMPTS + 1):
        try:
            response = _client().chat.completions.create(model=model, messages=messages)
        except Exception as exc:
            if _status_of(exc) in _AUTH_STATUS:
                error: LLMError = LLMAuthError(_auth_message(_status_of(exc)))
                _record_failure(error)
                raise error from exc
            if attempt < CALL_ATTEMPTS and _is_transient(exc):
                _sleep(BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS)) - 1])
                continue
            tries = f" after {attempt} tries" if attempt > 1 else ""
            error = LLMError(f"Model call failed{tries} ({_describe(exc)})")
            _record_failure(error)
            raise error from exc
        _record_ok()
        text = response.choices[0].message.content if response.choices else None
        text = _REASONING.sub("", text or "").strip()
        if not text:
            raise LLMError("The model returned no text content")
        return text
    raise AssertionError("unreachable")  # pragma: no cover


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
            return _validate(schema, _extract_json_object(raw))
        except (ValidationError, ValueError) as exc:
            last_error = exc
    raise LLMError(f"model output did not match {schema.__name__}: {last_error}") from last_error


def _validate(schema: type[BaseModel], text: str) -> BaseModel:
    """Validate the object, or the one object a reply wrapped it in, such as {"result": {...}}."""
    try:
        return schema.model_validate_json(text)
    except ValidationError:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and len(parsed) == 1:
            (inner,) = parsed.values()
            if isinstance(inner, dict):
                return schema.model_validate(inner)
        raise


def _client():
    from openai import OpenAI

    if _use_bedrock():
        return OpenAI(
            api_key=os.environ["AWS_BEARER_TOKEN_BEDROCK"],
            base_url=f"https://bedrock-runtime.{_region()}.amazonaws.com/openai/v1",
            timeout=REQUEST_TIMEOUT_SECONDS,
            max_retries=0,
        )
    return OpenAI(timeout=REQUEST_TIMEOUT_SECONDS, max_retries=0)


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
