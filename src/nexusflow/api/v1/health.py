from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from nexusflow.cache import redis
from nexusflow.db import get_db
from nexusflow.schemas import HealthResponse


router = APIRouter()


@router.get(
    "/live",
    response_model=dict[str, str],
)
async def liveness() -> dict[str, str]:
    """
    Liveness checks only the application process.

    Kubernetes/Docker should not restart the process merely
    because PostgreSQL or Redis is temporarily unavailable.
    """

    return {
        "status": "alive",
    }


@router.get(
    "/ready",
    response_model=HealthResponse,
)
async def readiness(
    db: AsyncSession = Depends(get_db),
) -> HealthResponse:
    database_status = "ok"

    redis_status = "ok"

    # ----------------------------------------------------------
    # PostgreSQL
    # ----------------------------------------------------------

    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        database_status = "error"

    # ----------------------------------------------------------
    # Redis
    # ----------------------------------------------------------

    try:
        await redis.ping()
    except Exception:
        redis_status = "error"

    overall_status = "ok" if (database_status == "ok" and redis_status == "ok") else "degraded"

    result = HealthResponse(
        status=overall_status,
        database=database_status,
        redis=redis_status,
    )

    # ----------------------------------------------------------
    # Readiness should fail when dependencies are unavailable.
    # ----------------------------------------------------------

    if overall_status != "ok":
        raise HTTPException(
            status_code=503,
            detail=result.model_dump(),
        )

    return result
