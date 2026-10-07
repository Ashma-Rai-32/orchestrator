"""The single provider adapter: the only module that knows how models are obtained.

Everything else asks for a `BaseChatModel` and never names a provider.
"""

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from staffroom_api.agents.fake import RuleBasedFakeModel

FAKE = "fake"


def chat_model(model: str) -> BaseChatModel:
    """`model` comes from settings: "fake", or "<provider>:<pinned model id>"."""
    if model == FAKE:
        return RuleBasedFakeModel()
    return init_chat_model(model, temperature=0)
