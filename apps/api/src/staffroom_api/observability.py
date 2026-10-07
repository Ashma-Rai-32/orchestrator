"""Tracing with Langfuse (ADR-0008). OpenTelemetry-based; LangChain via its callback handler.

- Each run is a Langfuse *session*, each tenant a Langfuse *user*: one trace per run
  segment, with every model call, tool call and delegation nested inside.
- `redact` runs on all data before export: secrets must never reach traces, even if a
  model or tool echoes one (defence in depth; agents only ever see secret *names*).
- Tracing is off unless Langfuse keys are configured.
"""

import json
import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langfuse import Langfuse, get_client, propagate_attributes
from langfuse._utils.serializer import EventSerializer  # what Langfuse exports with
from langfuse.langchain import CallbackHandler

from staffroom_api.settings import Settings

REDACTED = "[REDACTED]"
_SECRET_PATTERNS = [
    re.compile(r"eyJ[\w-]+\.[\w-]+\.[\w-]+"),  # JWTs (e.g. access tokens)
    re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_-]{16,}"),  # sk-... style API keys
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),  # AWS access key ids
    re.compile(r"(?i)\bbearer\s+[\w.~+/-]+=*"),  # Authorization header values
    re.compile(r"(?i)\b(api[_-]?key|secret|password|token)(\s*[:=]\s*)\S+"),  # key=value
]

_enabled = False


def redact(*, data: Any, **_: Any) -> Any:
    """Langfuse `mask` function: recursively replace secret-looking values."""
    if isinstance(data, str):
        for pattern in _SECRET_PATTERNS:
            data = pattern.sub(
                lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}" if m.lastindex else REDACTED,
                data,
            )
        return data
    if isinstance(data, dict):
        return {key: redact(data=value) for key, value in data.items()}
    if isinstance(data, list | tuple):
        return [redact(data=value) for value in data]
    if data is None or isinstance(data, bool | int | float):
        return data
    # Anything else (LangChain messages, LangGraph updates, ...) would be serialized by
    # Langfuse *after* masking. Serialize it the same way first, then redact the result.
    return redact(data=json.loads(json.dumps(data, cls=EventSerializer)))


def init_tracing(settings: Settings) -> bool:
    """Create the process-wide Langfuse client, if configured. Call once at startup."""
    global _enabled
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        _enabled = False
        return False
    Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key.get_secret_value(),
        base_url=settings.langfuse_base_url,
        environment=settings.environment,
        mask=redact,
    )
    _enabled = True
    return True


def shutdown_tracing() -> None:
    if _enabled:
        get_client().shutdown()  # flush buffered spans before the process exits


@contextmanager
def run_tracing(tenant_id: uuid.UUID, run_id: uuid.UUID) -> Iterator[list[BaseCallbackHandler]]:
    """Callbacks for one run segment, with run/tenant stamped on every span inside."""
    if not _enabled:
        yield []
        return
    with propagate_attributes(
        trace_name="run",
        session_id=str(run_id),
        user_id=str(tenant_id),
        tags=["staffroom"],
    ):
        yield [CallbackHandler()]
