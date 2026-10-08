"""Tenant secrets (ADR-0009). Agents only ever see names; values stay in the store.

`SecretStore` is the interface the rest of the app uses; `OpenBaoSecretStore` is the
implementation (OpenBao KV v2 through `hvac`, which speaks the Vault API).
"""

import asyncio
import re
import uuid
from typing import Protocol

import hvac
from hvac.exceptions import InvalidPath

# Environment-variable style, so values can be injected into the sandbox as env vars.
NAME = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
_MOUNT = "secret"


class InvalidSecretName(ValueError):
    pass


class SecretStore(Protocol):
    async def put(self, tenant_id: uuid.UUID, name: str, value: str) -> None: ...
    async def get(self, tenant_id: uuid.UUID, name: str) -> str | None: ...
    async def names(self, tenant_id: uuid.UUID) -> list[str]: ...


def check_name(name: str) -> str:
    if not NAME.fullmatch(name):
        raise InvalidSecretName(
            "Use capitals, digits and underscores, starting with a letter (e.g. OPENAI_API_KEY)."
        )
    return name


class OpenBaoSecretStore:
    """KV v2 at `secret/tenants/<tenant_id>/<NAME>`. hvac is synchronous: run it in a thread."""

    def __init__(self, url: str, token: str) -> None:
        self._client = hvac.Client(url=url, token=token, timeout=5)

    @staticmethod
    def _path(tenant_id: uuid.UUID, name: str = "") -> str:
        return f"tenants/{tenant_id}/{name}"

    async def put(self, tenant_id: uuid.UUID, name: str, value: str) -> None:
        await asyncio.to_thread(
            self._client.secrets.kv.v2.create_or_update_secret,
            path=self._path(tenant_id, check_name(name)),
            secret={"value": value},
            mount_point=_MOUNT,
        )

    async def get(self, tenant_id: uuid.UUID, name: str) -> str | None:
        try:
            response = await asyncio.to_thread(
                self._client.secrets.kv.v2.read_secret_version,
                path=self._path(tenant_id, check_name(name)),
                mount_point=_MOUNT,
                raise_on_deleted_version=True,
            )
        except InvalidPath:
            return None
        return str(response["data"]["data"]["value"])

    async def names(self, tenant_id: uuid.UUID) -> list[str]:
        try:
            response = await asyncio.to_thread(
                self._client.secrets.kv.v2.list_secrets,
                path=self._path(tenant_id),
                mount_point=_MOUNT,
            )
        except InvalidPath:  # nothing stored for this tenant yet
            return []
        return sorted(response["data"]["keys"])
