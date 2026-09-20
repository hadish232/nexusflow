from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nexusflow.api.v1.pagination import (
    decode_cursor,
    encode_cursor,
)
from nexusflow.cache import (
    get_cached_job,
    set_cached_job,
)
from nexusflow.db import get_db
from nexusflow.dependencies import (
    CurrentOrganizationID,
    CurrentUser,
)
from nexusflow.models import (
    IdempotencyKey,
    Job,
    JobStatus,
    OutboxEvent,
)
from nexusflow.rate_limit import (
    enforce_job_rate_limits,
)
from nexusflow.schemas import (
    JobCreate,
    JobListResponse,
    JobRead,
)


router = APIRouter()


IDEMPOTENCY_TTL_HOURS = 24


def request_hash(
    payload: JobCreate,
) -> str:
    canonical = json.dumps(
        payload.model_dump(),
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ============================================================
# Create job
# ============================================================


@router.post(
    "",
    response_model=JobRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_job(
    payload: JobCreate,
    current_user: CurrentUser,
    organization_id: CurrentOrganizationID,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
    ),
) -> JobRead:

    # ----------------------------------------------------------
    # Rate limiting
    # ----------------------------------------------------------

    await enforce_job_rate_limits(
        request=request,
        organization_id=organization_id,
        response=response,
    )

    # ----------------------------------------------------------
    # Idempotency-Key validation
    # ----------------------------------------------------------

    if not idempotency_key:
        raise HTTPException(
            status_code=400,
            detail=("Idempotency-Key header is required"),
        )

    if len(idempotency_key) > 255:
        raise HTTPException(
            status_code=400,
            detail=("Idempotency-Key must not exceed 255 characters"),
        )

    body_hash = request_hash(payload)

    expires_at = datetime.now(timezone.utc) + timedelta(hours=IDEMPOTENCY_TTL_HOURS)

    # ----------------------------------------------------------
    # Atomically claim the idempotency key.
    # ----------------------------------------------------------

    statement = (
        insert(IdempotencyKey)
        .values(
            organization_id=organization_id,
            key=idempotency_key,
            request_hash=body_hash,
            expires_at=expires_at,
        )
        .on_conflict_do_nothing(
            index_elements=[
                "organization_id",
                "key",
            ]
        )
    )

    result = await db.execute(statement)

    # ----------------------------------------------------------
    # Key already exists.
    # ----------------------------------------------------------

    if result.rowcount == 0:
        existing = await db.scalar(
            select(IdempotencyKey).where(
                IdempotencyKey.organization_id == organization_id,
                IdempotencyKey.key == idempotency_key,
            )
        )

        if existing is None:
            raise HTTPException(
                status_code=409,
                detail=("Unable to resolve idempotency request"),
            )

        if existing.request_hash != body_hash:
            raise HTTPException(
                status_code=409,
                detail=("Idempotency-Key was already used with a different request"),
            )

        if existing.response_body is not None:
            return JobRead.model_validate(existing.response_body)

        raise HTTPException(
            status_code=409,
            detail=("Request with this Idempotency-Key is already being processed"),
        )

    # ----------------------------------------------------------
    # Create job
    # ----------------------------------------------------------

    job = Job(
        organization_id=organization_id,
        created_by=current_user.id,
        job_type=payload.job_type,
        status=JobStatus.PENDING,
        payload=payload.payload,
    )

    db.add(job)

    await db.flush()

    # ----------------------------------------------------------
    # Transactional outbox event
    # ----------------------------------------------------------

    event = OutboxEvent(
        organization_id=organization_id,
        event_type="job.created",
        aggregate_type="job",
        aggregate_id=job.id,
        payload={
            "job_id": str(job.id),
            "organization_id": str(organization_id),
        },
    )

    db.add(event)

    # ----------------------------------------------------------
    # Prepare response before commit
    # ----------------------------------------------------------

    job_response = JobRead.model_validate(job)

    response_body = job_response.model_dump(mode="json")

    idempotency_record = await db.scalar(
        select(IdempotencyKey).where(
            IdempotencyKey.organization_id == organization_id,
            IdempotencyKey.key == idempotency_key,
        )
    )

    if idempotency_record is not None:
        idempotency_record.response_status = status.HTTP_201_CREATED

        idempotency_record.response_body = response_body

    # ----------------------------------------------------------
    # ONE transaction:
    #
    # jobs
    # idempotency_keys
    # outbox_events
    #
    # are committed together.
    # ----------------------------------------------------------

    await db.commit()

    return job_response


# ============================================================
# List jobs
# ============================================================


@router.get(
    "",
    response_model=JobListResponse,
)
async def list_jobs(
    organization_id: CurrentOrganizationID,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(
        default=50,
        ge=1,
        le=100,
    ),
    cursor: str | None = Query(
        default=None,
    ),
    job_status: JobStatus | None = Query(
        default=None,
        alias="status",
    ),
    job_type: str | None = Query(
        default=None,
        max_length=100,
    ),
) -> JobListResponse:

    # ----------------------------------------------------------
    # Base query
    #
    # Tenant filtering happens at the DB query level.
    # ----------------------------------------------------------

    statement = (
        select(Job)
        .where(Job.organization_id == organization_id)
        .order_by(
            Job.created_at.desc(),
            Job.id.desc(),
        )
        .limit(limit + 1)
    )

    # ----------------------------------------------------------
    # Optional filters
    # ----------------------------------------------------------

    if job_status is not None:
        statement = statement.where(Job.status == job_status)

    if job_type is not None:
        statement = statement.where(Job.job_type == job_type)

    # ----------------------------------------------------------
    # Cursor
    # ----------------------------------------------------------

    if cursor:
        try:
            cursor_created_at, cursor_id = decode_cursor(cursor)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=str(exc),
            ) from exc

        statement = statement.where(
            or_(
                Job.created_at < cursor_created_at,
                and_(
                    Job.created_at == cursor_created_at,
                    Job.id < cursor_id,
                ),
            )
        )

    result = await db.execute(statement)

    jobs = list(result.scalars().all())

    has_more = len(jobs) > limit

    if has_more:
        jobs = jobs[:limit]

    next_cursor = None

    if has_more and jobs:
        last_job = jobs[-1]

        next_cursor = encode_cursor(
            created_at=last_job.created_at,
            job_id=last_job.id,
        )

    return JobListResponse(
        items=[JobRead.model_validate(job) for job in jobs],
        next_cursor=next_cursor,
    )


# ============================================================
# Get job
# ============================================================


@router.get(
    "/{job_id}",
    response_model=JobRead,
)
async def get_job(
    job_id: uuid.UUID,
    organization_id: CurrentOrganizationID,
    db: AsyncSession = Depends(get_db),
) -> JobRead:

    # ----------------------------------------------------------
    # Redis cache
    # ----------------------------------------------------------

    cached = await get_cached_job(
        organization_id=organization_id,
        job_id=job_id,
    )

    if cached is not None:
        cached_job = JobRead.model_validate(cached)

        # Defensive tenant check.
        if cached_job.organization_id == organization_id:
            return cached_job

    # ----------------------------------------------------------
    # Database
    # ----------------------------------------------------------

    job = await db.scalar(
        select(Job).where(
            Job.id == job_id,
            Job.organization_id == organization_id,
        )
    )

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Job not found",
        )

    response = JobRead.model_validate(job)

    # ----------------------------------------------------------
    # Only cache terminal states.
    # ----------------------------------------------------------

    if job.status in {
        JobStatus.SUCCESS,
        JobStatus.FAILED,
    }:
        await set_cached_job(
            organization_id=organization_id,
            job_id=job_id,
            value=response.model_dump(mode="json"),
        )

    return response
