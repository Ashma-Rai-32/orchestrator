# 0006. Sandboxed code execution via deepagents backends (Docker locally, E2B in production)

- Status: accepted
- Date: 2026-10-07

## Context and problem

Employees write and run code (npm installs, builds, tests, later Playwright). That code is untrusted: it comes from a model steered by tenant input. The brief: generated code runs only in a sandbox; evaluate Docker-with-limits versus hosted sandboxes; write no custom isolation logic. The keyless five-minute local run should keep working.

## Decision drivers

- Strong isolation from our hosts, databases and secrets.
- A per-run workspace that persists across tool calls (and a worker crash).
- Tools for agents (read, write, edit, grep, execute) without writing a tool layer.
- Swappable by configuration; keyless local development.

## Options considered (checked 2026-10-07)

1. **Docker containers with hardening flags** (Docker SDK `docker` 7.2.0): self-hosted, keyless. Isolation is the shared kernel plus Docker's own controls; optional gVisor (`runsc`) runtime. The worker needs Docker API access, which is root-equivalent on that host.
2. **E2B** (`e2b` 2.53.1, official `langchain-e2b` 0.0.6 from e2b-dev, MIT): Firecracker microVMs, no sandbox infrastructure, needs an API key. `langchain-e2b` currently pins `deepagents<0.7` (we use 0.7.22).
3. **Modal** (`langchain-modal`): hosted gVisor sandboxes; needs an account.
4. **Daytona** (`langchain-daytona`): the open-source `daytonaio/daytona` repository is archived (July 2026); hosted only.
5. **`langchain-docker` 0.1.0**: no source repository or author listed; no wheel downloadable. Not trusted.

Tooling: **deepagents 0.7.22** (LangChain, MIT) defines `SandboxBackendProtocol` and `BaseSandbox`, which builds every file tool on four primitives (`execute`, `upload_files`, `download_files`, `id`), and `FilesystemMiddleware`, which gives a `create_agent` agent those tools.

## Decision

Option 1 for local development and CI, option 2 for anything running real untrusted code or going public, both behind deepagents' backend protocol and selected by `SANDBOX_BACKEND=docker|e2b`.

Docker backend (`staffroom_api/sandbox/docker_backend.py`) is a thin adapter; isolation is Docker configuration only:

- Image `staffroom-sandbox` (Node 24 + Python 3, non-root `node` user).
- `cap_drop=ALL`, `no-new-privileges`, read-only root filesystem, `/tmp` tmpfs, memory/CPU/PID limits, optional `runtime=runsc`.
- One named volume per run mounted at `/workspace`, so files survive a worker crash; the container is re-attached by name on resume.
- Command time limits use coreutils `timeout` inside the image.
- The worker reaches Docker through `tecnativa/docker-socket-proxy` (v0.5.0), which only exposes the container, exec, volume and image endpoints.

## Consequences

- Good: agents get file and execute tools from the framework; Staffroom code is one adapter.
- Good: the production backend is a config switch to microVMs.
- Bad: Docker locally is not a security boundary we would expose publicly; access to the Docker API (even proxied) allows creating privileged containers. Documented; production uses E2B.
- Bad: network egress is open in the sandbox (npm needs the registry). Follow-up: egress allowlist proxy.
- Follow-up: delete per-run volumes after deploy/retention (M6).

## Sources

- Installed source: deepagents 0.7.22 `backends/protocol.py`, `backends/sandbox.py`; langchain-e2b 0.0.6 METADATA.
- PyPI and GitHub metadata for docker, e2b, modal, daytona, microsandbox, deepagents, langchain-* integrations (2026-10-07).
