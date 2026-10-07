# 0003. Authentication with Keycloak organizations

- Status: accepted
- Date: 2026-10-07

## Context and problem

Tenant admins (non-technical founders) must sign in; every API call and WebSocket must be tied to exactly one tenant, which then drives Postgres RLS (ADR-0005). The brief: use an existing library or service, do not hand-roll auth. The local stack must still run in about five minutes without third-party accounts.

## Decision drivers

- Organizations as a first-class concept (organization = tenant).
- Standard OIDC/JWT, verifiable in FastAPI with a maintained library.
- Self-hostable in compose, configuration as code (no click-ops, no bootstrap scripts).
- Active maintenance.

## Options considered (checked 2026-10-07)

1. **Keycloak 26.8.0**: organizations built in (since 26.0); realm configuration imported from JSON at startup; one container (dev mode uses an embedded store). Heavier JVM, ~8 s start here. Apache-2.0, CNCF.
2. **Logto 1.44.0**: organizations first-class in the OSS core, one container, polished sign-in UX. App and API-resource setup needs a bootstrap script against its Management API. MPL-2.0.
3. **Zitadel 4.19.4**: strongest organization model, but the v4 compose stack is four containers (Traefik, API, Next.js login, Postgres).
4. **Hosted (Clerk, WorkOS)**: no containers, best UX; every developer needs an account and keys, breaking the keyless local run; vendor lock-in.
5. **fastapi-users**: no organization concept; README mentions maintenance mode.

Libraries for verifying tokens: PyJWT 2.15.1 (active; `PyJWKClient` fetches and caches JWKS) and Authlib 1.8.0 (active). python-jose is stale (last release May 2025).

## Decision

Keycloak (chosen by the maintainer), with:

- Realm `staffroom` in `infra/keycloak/staffroom-realm.json`, imported on first start: clients `staffroom-office` (public, PKCE, for the Phaser app) and `staffroom-dev-cli` (**dev only**, password grant for curl and tests), two demo organizations with pinned ids and one founder each.
- Tokens carry `aud: staffroom-api` (audience mapper) and a `tenants` claim `{alias: {id}}` from an organization-membership mapper with `addOrganizationId=true`. The built-in `organization` scope only emits aliases; a separate claim avoids redefining built-in scopes.
- **Tenant id = Keycloak organization id.**
- The API verifies tokens with PyJWT (signature via JWKS, `iss`, `aud`, `exp`) and requires exactly one organization in `tenants`.
- `KC_HOSTNAME` is fixed so the issuer is identical for the host and containers.

## Consequences

- Good: no auth code beyond token verification; realm is reviewable config.
- Good: organization invites, SSO and MFA come from Keycloak when needed.
- Bad: JVM footprint; dev mode only locally. Production needs `start` with a real database and TLS (Terraform milestone).
- Bad: users in several organizations must choose one (request scope `organization:<alias>`); the API rejects ambiguous tokens.
- The dev-only password-grant client must never exist outside local dev.

## Sources

- Keycloak 26.8.0 source: `OrganizationMembershipMapper.java`, `OAuth2Constants.java`; token inspected from the running realm.
- GitHub releases (2026-10-07): keycloak 26.8.0, logto v1.44.0, zitadel v4.19.4, authentik 2026.8.3; PyPI: PyJWT 2.15.1, Authlib 1.8.0, python-jose 3.5.0, fastapi-users 15.0.5.
