# Image for employees' sandboxes (ADR-0006). Runs as the unprivileged `node` user.
# Python 3 is required: deepagents' BaseSandbox runs small Python helpers for read/edit.
FROM node:24-bookworm-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Browser for checking built sites: Microsoft's Playwright MCP server + Chromium, installed
# with the exact Playwright version the MCP package depends on (matching browser build).
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN npm install -g @playwright/mcp@0.0.83 \
 && node /usr/local/lib/node_modules/@playwright/mcp/node_modules/playwright/cli.js \
      install --with-deps chromium \
 && rm -rf /var/lib/apt/lists/* /root/.npm

RUN mkdir /workspace && chown node:node /workspace
USER node
WORKDIR /workspace
ENV HOME=/tmp NPM_CONFIG_CACHE=/tmp/.npm

# Live preview of the workspace (testers' browser, and later the admin's deploy preview).
# Real-model finding: a model could not keep its own server alive across separate
# commands, so the sandbox provides one. Loopback only: nothing outside can reach it.
EXPOSE 4173
CMD ["python3", "-m", "http.server", "4173", "--bind", "127.0.0.1", "--directory", "/workspace"]
