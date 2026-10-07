"""Secrets never reach traces: the Langfuse mask function (ADR-0008)."""

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from staffroom_api.observability import REDACTED, init_tracing, redact
from staffroom_api.settings import Settings


@pytest.mark.parametrize(
    "secret",
    [
        "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl",  # a JWT
        "sk-ant-api03-AbCdEfGhIjKlMnOpQrStUvWx",  # provider API key
        "AKIAABCDEFGHIJKLMNOP",  # AWS access key id
    ],
)
def test_secret_values_are_redacted_anywhere_in_the_payload(secret: str) -> None:
    payload = {"messages": [{"content": f"use {secret} please"}], "meta": (f"x {secret}",)}
    masked = str(redact(data=payload))
    assert secret not in masked
    assert REDACTED in masked


def test_key_value_and_bearer_forms_keep_the_name_but_not_the_value() -> None:
    masked = redact(data="api_key=abc123 and Authorization: Bearer abc.def-ghi")
    assert masked == f"api_key={REDACTED} and Authorization: {REDACTED}"


def test_framework_objects_are_redacted_too() -> None:
    """Live finding: LangGraph outputs carry message objects, not plain dicts."""
    secret = "sk-test-1234567890abcdefXYZ"
    output = {
        "messages": [AIMessage(content=f"Done. key {secret}")],
        "update": HumanMessage(secret),
    }
    masked = str(redact(data=output))
    assert secret not in masked
    assert REDACTED in masked


def test_ordinary_text_is_untouched() -> None:
    text = "Build a landing page with a pricing table"
    assert redact(data=text) == text
    assert redact(data=42) == 42


def test_tracing_is_off_without_keys() -> None:
    assert init_tracing(Settings(langfuse_public_key=None, langfuse_secret_key=None)) is False
