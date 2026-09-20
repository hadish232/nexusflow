from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexusflow.db import get_db
from nexusflow.dependencies import CurrentOrganizationID
from nexusflow.models import Organization
from nexusflow.schemas import OrganizationRead


router = APIRouter()


@router.get(
    "/current",
    response_model=OrganizationRead,
)
async def current_tenant(
    organization_id: CurrentOrganizationID,
    db: AsyncSession = Depends(get_db),
) -> OrganizationRead:
    organization = await db.scalar(
        select(Organization).where(
            Organization.id == organization_id
        )
    )

    if organization is None:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=404,
            detail="Organization not found",
        )

    return OrganizationRead.model_validate(organization)