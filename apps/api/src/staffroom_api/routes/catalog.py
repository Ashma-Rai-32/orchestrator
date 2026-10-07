from fastapi import APIRouter

from staffroom_api.skills.catalog import Skill, load_catalog

router = APIRouter(tags=["catalog"])


@router.get("/skills")
async def list_skills() -> list[Skill]:
    """The skills a tenant can hire for. Platform-wide, no tenant needed."""
    return list(load_catalog().values())
