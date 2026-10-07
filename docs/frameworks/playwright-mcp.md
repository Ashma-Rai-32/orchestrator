# Playwright MCP + langchain-mcp-adapters (@playwright/mcp 0.0.83, langchain-mcp-adapters 0.3.2, mcp 1.30.0, checked 2026-10-07)

Code: `apps/api/src/staffroom_api/sandbox/browser.py`, tests in `apps/api/tests/test_browser.py`. Findings from running it inside the sandbox and reading the installed source.

## What it can do

- **Playwright MCP** (Microsoft) exposes a real browser as MCP tools: navigate, click, type, fill forms, screenshots, console and network inspection, tabs (25 tools in 0.0.83).
- **`browser_snapshot` returns the page's accessibility tree** inline (`heading "Chat with Acme AI"`, `button "Send"`, each with a `ref` to click/type). Models "see" the page without vision.
- **langchain-mcp-adapters** turns any MCP server into LangChain tools (`load_mcp_tools(session)`), over stdio, streamable HTTP, SSE or WebSocket.
- **stdio over `docker exec -i`** works: the MCP server runs inside the sandbox container next to the site, with no network port exposed.

## What it cannot do

- `--allowed-origins` / `--blocked-origins` are, per its README, **not a security boundary**. Isolation must come from where the browser runs (our sandbox).
- No `chromium` in the documented `--browser` values (chrome, firefox, webkit, msedge), and Google Chrome has no Linux ARM build. `--browser=chromium` with Playwright's own Chromium works anyway (verified).

## Gotchas

- **`MultiServerMCPClient.get_tools()` opens a new session per tool call**: for a browser, every call would get a fresh browser. Keep one `client.session(...)` open and `load_mcp_tools(session)` from it.
- **stdio servers inherit only a small subset of environment variables**: pass `DOCKER_HOST` (and `PATH`) explicitly in the connection's `env`.
- **langchain-mcp-adapters pins `mcp<2.0`** while the MCP SDK is at 2.3.0; uv resolves mcp 1.30.0.
- Chromium's own sandbox needs Linux capabilities we drop in the container: run with `--no-sandbox` (the container is the sandbox).
- Read-only root filesystem: use `--isolated` (profile in memory) and an `--output-dir` under `/tmp`.
- Install browsers with the Playwright version bundled in `@playwright/mcp` (`node_modules/playwright/cli.js install --with-deps chromium`) so browser build and client match.
- Image size: the sandbox image grows to ~1.4 GB with Chromium.
- Includes `browser_run_code_unsafe` and `browser_evaluate`; we offer a curated subset (least privilege for the model).

## Verdict: adopt

Browser checks run inside each run's sandbox; agents get a curated set of Playwright MCP tools through langchain-mcp-adapters, one session per run segment.
