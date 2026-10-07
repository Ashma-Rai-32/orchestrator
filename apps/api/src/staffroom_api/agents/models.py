"""The single provider adapter: the only module that knows how models are obtained.

Everything else asks for a `BaseChatModel` and never names a provider.
"""

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from staffroom_api.agents.fake import RuleBasedFakeModel

FAKE = "fake"


def chat_model(model: str) -> BaseChatModel:
    """`model` comes from settings:

    - "fake"            deterministic, instant, no API key (tests, CI)
    - "fake:1.5"        same, but each reply takes 1.5 s (watch runs live, build the UI)
    - "<provider>:<id>" a real model via init_chat_model, e.g. "anthropic:claude-haiku-4-5-20251001"
    """
    name, _, arg = model.partition(":")
    if name == FAKE:
        return RuleBasedFakeModel(latency_seconds=float(arg or 0))
    return init_chat_model(model, temperature=0)
