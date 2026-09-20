from __future__ import annotations

import time
import uuid

from fastapi import HTTPException, Request, Response, status

from nexusflow.cache import redis
from nexusflow.config import settings


# ============================================================
# Atomic Redis fixed-window rate limiter
# ============================================================

RATE_LIMIT_SCRIPT = """
local current = redis.call('INCR', KEYS[1])

if current == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end

local ttl = redis.call('TTL', KEYS[1])

return {current, ttl}
"""


async def consume_rate_limit(
    *,
    key: str,
    limit: int,
    window_seconds: int,
) -> tuple[int, int]:
    result = await redis.eval(
        RATE_LIMIT_SCRIPT,
        1,
        key,
        window_seconds,
    )

    current = int(result[0])

    retry_after = max(
        int(result[1]),
        1,
    )

    remaining = max(
        limit - current,
        0,
    )

    if current > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(retry_after),
            },
        )

    return remaining, retry_after


def current_window(
    window_seconds: int,
) -> int:
    return int(time.time() // window_seconds)


async def enforce_job_rate_limits(
    *,
    request: Request,
    organization_id: uuid.UUID,
    response: Response,
) -> None:
    window_seconds = settings.job_rate_limit_window_seconds

    window = current_window(window_seconds)

    # ----------------------------------------------------------
    # IP limit
    # ----------------------------------------------------------

    client_ip = request.client.host if request.client else "unknown"

    ip_key = f"nexusflow:v1:rate-limit:ip:{client_ip}:{window}"

    ip_remaining, ip_reset = await consume_rate_limit(
        key=ip_key,
        limit=settings.job_rate_limit_per_ip,
        window_seconds=window_seconds,
    )

    # ----------------------------------------------------------
    # Organization / tenant limit
    # ----------------------------------------------------------

    tenant_key = f"nexusflow:v1:rate-limit:tenant:{organization_id}:{window}"

    tenant_remaining, tenant_reset = await consume_rate_limit(
        key=tenant_key,
        limit=settings.job_rate_limit_per_tenant,
        window_seconds=window_seconds,
    )

    # ----------------------------------------------------------
    # Response headers
    # ----------------------------------------------------------

    response.headers["X-RateLimit-IP-Limit"] = str(settings.job_rate_limit_per_ip)

    response.headers["X-RateLimit-IP-Remaining"] = str(ip_remaining)

    response.headers["X-RateLimit-IP-Reset"] = str(ip_reset)

    response.headers["X-RateLimit-Tenant-Limit"] = str(settings.job_rate_limit_per_tenant)

    response.headers["X-RateLimit-Tenant-Remaining"] = str(tenant_remaining)

    response.headers["X-RateLimit-Tenant-Reset"] = str(tenant_reset)
