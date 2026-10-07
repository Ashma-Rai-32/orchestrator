import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from staffroom_api.deps import CurrentPrincipal

router = APIRouter(tags=["tenants"])


class Me(BaseModel):
    user_id: str
    tenant_id: uuid.UUID
    tenant_name: str


@router.get("/me")
async def me(principal: CurrentPrincipal) -> Me:
    """Who is signed in, and which tenant (Keycloak organization) they act for.

    Tenants are created in Keycloak (organizations); the first request from an
    organization creates its row here.
    """
    return Me(
        user_id=principal.user_id,
        tenant_id=principal.tenant_id,
        tenant_name=principal.tenant_name,
    )
