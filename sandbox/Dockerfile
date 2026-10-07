# Image for employees' sandboxes (ADR-0006). Runs as the unprivileged `node` user.
# Python 3 is required: deepagents' BaseSandbox runs small Python helpers for read/edit.
FROM node:24-bookworm-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN mkdir /workspace && chown node:node /workspace
USER node
WORKDIR /workspace
ENV HOME=/tmp NPM_CONFIG_CACHE=/tmp/.npm

CMD ["sleep", "infinity"]
