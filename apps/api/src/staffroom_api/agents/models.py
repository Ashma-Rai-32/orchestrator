"""The single provider adapter: the only module that knows how models are obtained.

Everything else asks for a `BaseChatModel` and never names a provider.
"""

from functools import cache

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.rate_limiters import InMemoryRateLimiter

from staffroom_api.agents.fake import RuleBasedFakeModel

FAKE = "fake"


@cache
def _shared_limiter(requests_per_second: float) -> InMemoryRateLimiter:
    """One token bucket per process, shared by every agent's model (free-tier quotas)."""
    return InMemoryRateLimiter(requests_per_second=requests_per_second, max_bucket_size=1)


def chat_model(model: str, requests_per_second: float | None = None) -> BaseChatModel:
    """`model` comes from settings:

    - "fake"            deterministic, instant, no API key (tests, CI)
    - "fake:1.5"        same, but each reply takes 1.5 s (watch runs live, build the UI)
    - "<provider>:<id>" a real model via init_chat_model, e.g.
                        "google_genai:<id>", "anthropic:<id>", "ollama:qwen3.5:4b"

    `requests_per_second` throttles real models (e.g. 0.15 = 9 requests/minute).
    """
    name, _, arg = model.partition(":")
    if name == FAKE:
        return RuleBasedFakeModel(latency_seconds=float(arg or 0))
    limiter = _shared_limiter(requests_per_second) if requests_per_second else None
    return init_chat_model(model, temperature=0, rate_limiter=limiter)
