from __future__ import annotations

import json
import uuid
from typing import Any

from redis.asyncio import Redis

from nexusflow.config import settings


redis = Redis.from_url(
    settings.redis_url,
    encoding="utf-8",
    decode_responses=True,
    health_check_interval=30,
)


JOB_CACHE_TTL_SECONDS = 60


def job_cache_key(
    organization_id: uuid.UUID,
    job_id: uuid.UUID,
) -> str:
    return (
        f"nexusflow:v1:"
        f"organization:{organization_id}:"
        f"job:{job_id}"
    )


async def get_cached_job(
    organization_id: uuid.UUID,
    job_id: uuid.UUID,
) -> dict[str, Any] | None:
    value = await redis.get(
        job_cache_key(
            organization_id,
            job_id,
        )
    )

    if value is None:
        return None

    try:
        return json.loads(value)
    except json.JSONDecodeError:
        # Corrupt cache data should never break the API.
        await redis.delete(
            job_cache_key(
                organization_id,
                job_id,
            )
        )

        return None


async def set_cached_job(
    organization_id: uuid.UUID,
    job_id: uuid.UUID,
    value: dict[str, Any],
    ttl: int = JOB_CACHE_TTL_SECONDS,
) -> None:
    await redis.set(
        job_cache_key(
            organization_id,
            job_id,
        ),
        json.dumps(
            value,
            separators=(",", ":"),
        ),
        ex=ttl,
    )


async def delete_cached_job(
    organization_id: uuid.UUID,
    job_id: uuid.UUID,
) -> None:
    await redis.delete(
        job_cache_key(
            organization_id,
            job_id,
        )
    )