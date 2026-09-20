import json
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from trueup.gateway import llm
from trueup.gateway.llm import LLMError, complete, complete_json


class FakeClient:
    """Stands in for openai.OpenAI. Replies are consumed in order; an Exception is raised."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        message = SimpleNamespace(content=reply)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.delenv("MODEL_ID", raising=False)

    def install(*replies):
        client = FakeClient(*replies)
        monkeypatch.setattr(llm, "_client", lambda: client)
        return client

    return install


def test_complete_returns_text_and_sends_system_then_user(fake):
    client = fake("hello")
    assert complete("say hello", system="be brief") == "hello"
    call = client.calls[0]
    assert call["model"] == llm.DEFAULT_MODEL
    assert call["messages"] == [
        {"role": "system", "content": "be brief"},
        {"role": "user", "content": "say hello"},
    ]


def test_complete_without_system_sends_only_user(fake):
    client = fake("hello")
    complete("say hello")
    assert client.calls[0]["messages"] == [{"role": "user", "content": "say hello"}]


def test_model_id_env_overrides_default_and_argument_overrides_env(fake, monkeypatch):
    client = fake("a", "b")
    monkeypatch.setenv("MODEL_ID", "gpt-env")
    complete("x")
    complete("x", model="gpt-arg")
    assert [c["model"] for c in client.calls] == ["gpt-env", "gpt-arg"]


def test_inline_reasoning_is_stripped_even_when_it_contains_braces(fake):
    fake('<reasoning>maybe {"label": "wrong"} hmm</reasoning>\n{"label": "right", "score": 1}')
    assert complete_json("classify this", Verdict).label == "right"


def test_reasoning_only_reply_raises(fake):
    fake("<reasoning>thinking and never answering</reasoning>")
    with pytest.raises(LLMError):
        complete("say hello")


def test_sdk_error_raises(fake):
    fake(RuntimeError("boom"))
    with pytest.raises(LLMError):
        complete("say hello")


def test_empty_content_raises(fake):
    fake("")
    with pytest.raises(LLMError):
        complete("say hello")


def test_available_reflects_credentials(monkeypatch):
    assert not llm.available()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert llm.available()
    monkeypatch.delenv("OPENAI_API_KEY")
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "token")
    assert llm.available()


def test_bedrock_uses_regional_endpoint_and_gpt_oss_default(monkeypatch):
    built: dict = {}

    class RecordingOpenAI:
        def __init__(self, **kwargs):
            built.update(kwargs)
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **kw: (
                        built.update(model=kw["model"])
                        or SimpleNamespace(
                            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
                        )
                    )
                )
            )

    monkeypatch.setattr("openai.OpenAI", RecordingOpenAI)
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "token")
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    assert complete("hi") == "ok"
    assert built["api_key"] == "token"
    assert built["base_url"] == "https://bedrock-runtime.us-west-2.amazonaws.com/openai/v1"
    assert built["model"] == llm.BEDROCK_DEFAULT_MODEL


def test_openai_key_wins_over_bedrock_token(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "token")
    assert not llm._use_bedrock()


class Verdict(BaseModel):
    label: str
    score: float


def test_complete_json_parses_model(fake):
    fake(json.dumps({"label": "match", "score": 0.9}))
    verdict = complete_json("classify this", Verdict)
    assert isinstance(verdict, Verdict)
    assert verdict.label == "match"


def test_complete_json_strips_code_fences(fake):
    fake("```json\n" + json.dumps({"label": "match", "score": 0.9}) + "\n```")
    assert complete_json("classify this", Verdict).score == 0.9


def test_complete_json_finds_object_inside_prose_with_braces_in_strings(fake):
    fake('Sure! Here it is: {"label": "a } tricky { one", "score": 1} Hope that helps.')
    assert complete_json("classify this", Verdict).label == "a } tricky { one"


def test_complete_json_retries_once_then_succeeds(fake):
    client = fake("not json at all", json.dumps({"label": "ok", "score": 0.5}))
    assert complete_json("classify this", Verdict).label == "ok"
    assert len(client.calls) == 2


def test_complete_json_invalid_shape_twice_raises(fake):
    client = fake('{"nope": true}', '{"nope": true}')
    with pytest.raises(LLMError):
        complete_json("classify this", Verdict)
    assert len(client.calls) == 2
