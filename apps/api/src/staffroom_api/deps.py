"""Request-scoped dependencies: who is calling, their tenant, and a tenant-scoped session."""

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, WebSocket, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from staffroom_api.auth import AuthError, Principal, TenantChoiceError, TokenVerifier
from staffroom_api.db.tenancy import tenant_transaction

_bearer = HTTPBearer(auto_error=False)
WS_SUBPROTOCOL = "bearer"  # browsers send ["bearer", <token>] as WebSocket subprotocols


async def _authenticate(verifier: TokenVerifier, engine: AsyncEngine, token: str) -> Principal:
    principal = await verifier.verify(token)
    await _ensure_tenant(engine, principal)
    return principal


async def _ensure_tenant(engine: AsyncEngine, principal: Principal) -> None:
    """First request from an organization creates its tenant row (id = Keycloak org id)."""
    async with tenant_transaction(engine, principal.tenant_id) as conn:
        await conn.execute(
            text("INSERT INTO tenants (id, name) VALUES (:id, :name) ON CONFLICT (id) DO NOTHING"),
            {"id": principal.tenant_id, "name": principal.tenant_name},
        )


async def current_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Principal:
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED, "Not signed in.", headers={"WWW-Authenticate": "Bearer"}
    )
    if credentials is None:
        raise unauthorized
    try:
        return await _authenticate(
            request.app.state.verifier, request.app.state.db, credentials.credentials
        )
    except AuthError as exc:
        raise unauthorized from exc
    except TenantChoiceError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc


async def websocket_principal(websocket: WebSocket) -> Principal | None:
    """Token from the `Sec-WebSocket-Protocol` header, never the URL (URLs end up in logs)."""
    protocols = websocket.scope.get("subprotocols", [])
    if len(protocols) != 2 or protocols[0] != WS_SUBPROTOCOL:
        return None
    try:
        return await _authenticate(
            websocket.app.state.verifier, websocket.app.state.db, protocols[1]
        )
    except (AuthError, TenantChoiceError):
        return None


async def _tenant_id(principal: Annotated[Principal, Depends(current_principal)]) -> uuid.UUID:
    return principal.tenant_id


async def _tenant_session(
    request: Request, tenant_id: Annotated[uuid.UUID, Depends(_tenant_id)]
) -> AsyncIterator[AsyncSession]:
    async with tenant_transaction(request.app.state.db, tenant_id) as conn:
        session = AsyncSession(bind=conn, expire_on_commit=False)
        yield session
        await session.flush()  # transaction commits when tenant_transaction exits


# scope="function": commit happens before the response is sent, so a 201 is never a lie.
TenantSession = Annotated[AsyncSession, Depends(_tenant_session, scope="function")]
TenantId = Annotated[uuid.UUID, Depends(_tenant_id)]
CurrentPrincipal = Annotated[Principal, Depends(current_principal)]
