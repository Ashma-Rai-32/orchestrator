"""Verify Keycloak access tokens and resolve the caller's tenant (ADR-0003).

PyJWT does the cryptography and standard claim checks; this module only decides
which claims Staffroom requires and how the tenant is read.
"""

import asyncio
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import jwt

from staffroom_api.settings import Settings

KeyResolver = Callable[[str], Any]  # token -> public key that signed it


class AuthError(Exception):
    """Token missing, invalid or expired (HTTP 401)."""


class TenantChoiceError(Exception):
    """Valid token, but not exactly one organization (HTTP 403)."""


@dataclass(frozen=True)
class Principal:
    user_id: str
    tenant_id: uuid.UUID
    tenant_name: str


class TokenVerifier:
    def __init__(self, issuer: str, audience: str, key_for: KeyResolver) -> None:
        self._issuer, self._audience, self._key_for = issuer, audience, key_for

    @classmethod
    def from_settings(cls, s: Settings) -> "TokenVerifier":
        # Fetches Keycloak's public keys and caches them (refetches on unknown `kid`).
        jwks = jwt.PyJWKClient(s.oidc_jwks_url, cache_keys=True)
        return cls(s.oidc_issuer, s.oidc_audience, lambda t: jwks.get_signing_key_from_jwt(t).key)

    async def verify(self, token: str) -> Principal:
        try:
            # PyJWKClient uses blocking HTTP on a cache miss: keep it off the event loop.
            key = await asyncio.to_thread(self._key_for, token)
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "iat", "sub", "iss", "aud"]},
            )
        except jwt.PyJWTError as exc:
            raise AuthError(type(exc).__name__) from exc  # never echo the token
        return _principal(claims)


def _principal(claims: dict[str, Any]) -> Principal:
    # Keycloak organization-membership mapper: {"<alias>": {"id": "<uuid>"}}
    orgs = claims.get("tenants") or {}
    if len(orgs) != 1:
        raise TenantChoiceError(
            "Token must name exactly one organization (request scope organization:<alias>)."
        )
    (alias, org), *_ = orgs.items()
    return Principal(user_id=claims["sub"], tenant_id=uuid.UUID(org["id"]), tenant_name=alias)
