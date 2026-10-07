# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "langchain==1.4.3",
#     "langchain-anthropic==1.7.5",
# ]
# ///
"""Spike: LangChain model interface, step 1.

Question: can we pick the model provider from config alone, and swap in a
deterministic fake model for tests, without changing calling code?

Run:  uv run spikes/langchain-models/main.py
Real: STAFFROOM_REAL_MODEL=1 ANTHROPIC_API_KEY=... uv run spikes/langchain-models/main.py
"""

import os

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

# Pinned model ID, not an alias (init_chat_model docs recommend this).
DEFAULT_MODEL = "anthropic:claude-haiku-4-5-20251001"


def get_model() -> BaseChatModel:
    """The only place that decides which model we get."""
    if os.environ.get("STAFFROOM_REAL_MODEL") == "1":
        return init_chat_model(os.environ.get("STAFFROOM_MODEL", DEFAULT_MODEL), temperature=0)
    return GenericFakeChatModel(
        messages=iter(
            [
                AIMessage(content="Hi! I'm a fake employee. I always say this first."),
                "And this second.",
            ]
        )
    )


def demo_same_calling_code() -> None:
    print("\n== 1. Same calling code, model chosen by config ==")
    model = get_model()
    print(f"model class: {type(model).__name__}")
    for question in ["Who are you?", "Anything else?"]:
        reply = model.invoke(question)
        print(f"Q: {question}\nA: {reply.content}")


def demo_configurable_model() -> None:
    print("\n== 2. One configurable model, provider picked per call ==")
    # No model given -> init_chat_model returns a lazy wrapper. Nothing is
    # constructed (and no API key is needed) until a call supplies the config.
    model = init_chat_model(configurable_fields=("model", "model_provider"), temperature=0)
    print(f"wrapper class: {type(model).__name__}")
    config = {"configurable": {"model": DEFAULT_MODEL}}
    print(f"a call with config={config} would build the real model on demand")


if __name__ == "__main__":
    demo_same_calling_code()
    demo_configurable_model()
