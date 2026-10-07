# LangChain model interface (langchain 1.4.3, langchain-core 1.6.7, checked 2026-10-07)

Spike: [spikes/langchain-models/](../../spikes/langchain-models/). Findings come from running it and from reading the installed source, not from memory.

## What it can do

- **Provider from config.** `init_chat_model("anthropic:claude-haiku-4-5-20251001")` returns a provider's chat model from a string. Swapping to Bedrock (`bedrock_converse:...`, `anthropic_bedrock:...`) or Gemini (`google_genai:...`) is a config change plus installing the integration package. 30+ providers are listed in the docstring.
- **Configurable model.** `init_chat_model(configurable_fields=("model", "model_provider"))` returns a lazy wrapper; the model is built per call from `config={"configurable": {...}}`. This could give each employee its own model via run config.
- **Fake models for tests.** `GenericFakeChatModel(messages=iter([...]))` replays scripted replies (strings or `AIMessage`s, including tool calls) in order. Deterministic, no network.
- **Tool calling.** `@tool` derives name, description and JSON schema from the signature and docstring. The model returns `AIMessage.tool_calls`; `tool.invoke(tool_call)` returns a `ToolMessage` linked by `tool_call_id`.
- **Structured output.** `model.with_structured_output(PydanticModel)` returns a validated instance. `include_raw=True` returns `{raw, parsed, parsing_error}` instead of raising, so callers can retry.
- **Rate limiting.** `rate_limiter=InMemoryRateLimiter(requests_per_second=...)` on any chat model (token bucket, blocks before each call).
- **Retries and fallbacks.** `.with_retry(retry_if_exception_type=..., stop_after_attempt=...)` and `.with_fallbacks([other_model], exceptions_to_handle=...)`.

## What it cannot do

- No fake model in `langchain-core` or `langchain-tests` implements `bind_tools` (the base class raises `NotImplementedError`), and therefore `with_structured_output` fails on them too. We need a 5-line subclass whose `bind_tools` returns `self`.
- `InMemoryRateLimiter` is per-process. It cannot limit across multiple workers; a shared limit would need Redis or provider-side quotas.
- The fake models do not check that a scripted tool call matches a bound tool. Tests can pass with tool names the real model would never be offered.

## Gotchas

- **Pin model IDs.** The `init_chat_model` docs recommend dated IDs over aliases so behaviour does not drift when an alias moves.
- **`configurable_fields="any"` is a security risk**: runtime config could change `api_key` or `base_url`. Always list allowed fields explicitly.
- **Bare model names infer the provider by prefix**, and `gemini...` maps to `google_vertexai` (the docs say this default will change). Always use the `provider:model` form.
- **`with_retry` / `with_fallbacks` return a `Runnable`, not a `BaseChatModel`.** You cannot pass the wrapped model to an agent. For agents, LangChain 1.x provides middleware instead: `ModelRetryMiddleware`, `ModelFallbackMiddleware`, `ModelCallLimitMiddleware`, `ToolRetryMiddleware`, `ToolCallLimitMiddleware` (explored in the LangGraph spikes).
- **Retries can multiply.** Provider clients already retry (`max_retries=`); adding `with_retry` on top multiplies attempts and latency.
- **Structured output defaults to the tool-calling trick**: the schema becomes a forced tool named after the class. Field descriptions and the class docstring are effectively prompt text. Anthropic also offers `method="json_schema"` (native structured outputs); not yet compared with a real model.
- **The rate limiter bucket starts empty**, so even the first call waits about `1 / requests_per_second`.
- **Tool return types pass through.** A tool returning `list[str]` produces a list `ToolMessage.content`, which providers may read as content blocks. Returning `str` is safer; to confirm with a real model.

## Verdict: adopt, behind one adapter module

- `init_chat_model` is the only way the app obtains models, called from `apps/api/.../agents/models.py` (the single provider adapter required by the brief).
- `FakeToolCallingModel` (5 lines) lives next to it for tests and CI.
- Use `with_structured_output(..., include_raw=True)` for coordinator plans.
- Use agent middleware (not `with_retry`/`with_fallbacks`) for resilience inside agents.

Still open: a real-model run (needs an API key), and comparing `function_calling` vs `json_schema` structured output.

## Sources

- Installed source: `langchain/chat_models/base.py` (`init_chat_model`), `langchain_core/language_models/fake_chat_models.py`, `langchain_core/language_models/chat_models.py` (`bind_tools`, `with_structured_output`), `langchain_core/rate_limiters.py`, `langchain_core/runnables/base.py`, `langchain/agents/middleware/`, `langchain_anthropic/chat_models.py` (1.7.5).
- Docs: https://docs.langchain.com/oss/python/integrations/providers
