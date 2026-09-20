from __future__ import annotations

from app.config import LLM_ENABLED
from app.services.llm.stub import StubLLM

_client = None


def get_llm():
    """Gemini when a key is present, otherwise the deterministic stub.

    Acceptance test 18 depends on this: with no GEMINI_API_KEY the entire
    simulation must still run end to end.
    """
    global _client
    if _client is None:
        if LLM_ENABLED:
            from app.services.llm.gemini import GeminiLLM

            _client = GeminiLLM()
        else:
            _client = StubLLM()
    return _client


def set_llm(client) -> None:
    global _client
    _client = client
