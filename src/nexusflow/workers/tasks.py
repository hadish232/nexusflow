from __future__ import annotations

import os
import random
import time
import uuid
from datetime import datetime, timezone

from celery import shared_task
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from nexusflow.config import settings
from nexusflow.models import (
    Job,
    JobAttempt,
    JobStatus,
    OutboxEvent,
    OutboxStatus,
)


# ============================================================
# Sync PostgreSQL engine for Celery workers
# ============================================================

sync_engine = create_engine(
    settings.database_url_sync,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_recycle=1800,
)


SessionLocal = sessionmaker(
    bind=sync_engine,
    expire_on_commit=False,
)


WORKER_ID = os.environ.get(
    "HOSTNAME",
    "unknown",
)


def next_attempt_number(
    session: Session,
    job_id: uuid.UUID,
) -> int:
    current_max = session.scalar(
        select(func.max(JobAttempt.attempt_number)).where(JobAttempt.job_id == job_id)
    )

    return int(current_max or 0) + 1


# ============================================================
# Execute Job
# ============================================================


@shared_task(
    bind=True,
    max_retries=None,
    name="nexusflow.workers.tasks.execute_job",
)
def execute_job(
    self,
    job_id: str,
) -> dict[str, str]:
    parsed_job_id = uuid.UUID(job_id)

    # ----------------------------------------------------------
    # Claim execution
    # ----------------------------------------------------------

    with SessionLocal.begin() as session:
        job = session.scalar(select(Job).where(Job.id == parsed_job_id).with_for_update())

        if job is None:
            return {
                "status": "ignored",
                "reason": "job-not-found",
            }

        # ------------------------------------------------------
        # Duplicate delivery protection
        # ------------------------------------------------------

        if job.status == JobStatus.SUCCESS:
            return {
                "status": "already-complete",
                "job_id": job_id,
            }

        if job.status == JobStatus.RUNNING:
            return {
                "status": "already-running",
                "job_id": job_id,
            }

        # Only these states are executable.
        if job.status not in {
            JobStatus.PENDING,
            JobStatus.QUEUED,
            JobStatus.FAILED,
        }:
            return {
                "status": "ignored",
                "reason": (f"invalid-state:{job.status}"),
            }

        attempt_number = next_attempt_number(
            session,
            parsed_job_id,
        )

        job.status = JobStatus.RUNNING
        job.error = None

        attempt = JobAttempt(
            job_id=parsed_job_id,
            attempt_number=attempt_number,
            started_at=datetime.now(timezone.utc),
            worker_id=WORKER_ID,
            status="RUNNING",
        )

        session.add(attempt)

        payload = dict(job.payload)

    # ----------------------------------------------------------
    # Execute outside database transaction.
    #
    # This is important: a long-running task should not keep a
    # PostgreSQL transaction open.
    # ----------------------------------------------------------

    try:
        # Simulated work.
        #
        # The real executor will eventually dispatch to:
        #
        # HTTP
        # Python functions
        # CPU workers
        # workflow DAG nodes
        #
        time.sleep(0.25)

        # ------------------------------------------------------
        # Useful failure testing
        #
        # payload:
        # {
        #   "fail_until_attempt": 2
        # }
        #
        # causes attempts 1 and 2 to fail.
        # ------------------------------------------------------

        fail_until_attempt = int(
            payload.get(
                "fail_until_attempt",
                0,
            )
        )

        if fail_until_attempt and attempt_number <= fail_until_attempt:
            raise RuntimeError(f"Simulated transient failure on attempt {attempt_number}")

        if payload.get(
            "force_failure",
            False,
        ):
            raise RuntimeError("Simulated permanent failure")

        # ------------------------------------------------------
        # SUCCESS
        # ------------------------------------------------------

        with SessionLocal.begin() as session:
            job = session.scalar(select(Job).where(Job.id == parsed_job_id).with_for_update())

            if job is None:
                return {
                    "status": "ignored",
                    "reason": "job-deleted",
                }

            job.status = JobStatus.SUCCESS

            job.result = {
                "message": ("Job executed successfully"),
                "job_id": job_id,
                "attempt": str(attempt_number),
                "worker_id": WORKER_ID,
            }

            job.error = None

            attempt = session.scalar(
                select(JobAttempt).where(
                    JobAttempt.job_id == parsed_job_id,
                    JobAttempt.attempt_number == attempt_number,
                )
            )

            if attempt is not None:
                attempt.status = "SUCCESS"

                attempt.finished_at = datetime.now(timezone.utc)

        return {
            "status": "success",
            "job_id": job_id,
        }

    # ----------------------------------------------------------
    # FAILURE
    # ----------------------------------------------------------

    except Exception as exc:
        current_retry = self.request.retries

        with SessionLocal.begin() as session:
            job = session.scalar(select(Job).where(Job.id == parsed_job_id).with_for_update())

            if job is None:
                return {
                    "status": "ignored",
                    "reason": "job-deleted",
                }

            attempt = session.scalar(
                select(JobAttempt).where(
                    JobAttempt.job_id == parsed_job_id,
                    JobAttempt.attempt_number == attempt_number,
                )
            )

            if attempt is not None:
                attempt.status = "FAILED"

                attempt.finished_at = datetime.now(timezone.utc)

                attempt.error_type = type(exc).__name__

                attempt.error_message = str(exc)

            # --------------------------------------------------
            # Retry
            # --------------------------------------------------

            if current_retry < settings.job_max_retries:
                job.status = JobStatus.QUEUED

                job.error = str(exc)

            # --------------------------------------------------
            # Permanent failure
            # --------------------------------------------------

            else:
                job.status = JobStatus.FAILED

                job.error = str(exc)

        # ------------------------------------------------------
        # Ask Celery to retry.
        # ------------------------------------------------------

        if current_retry < settings.job_max_retries:
            exponential_delay = min(
                2 ** (current_retry + 1),
                settings.job_retry_max_delay,
            )

            jitter = random.randint(
                0,
                3,
            )

            raise self.retry(
                exc=exc,
                countdown=(exponential_delay + jitter),
            ) from exc

        return {
            "status": "failed",
            "job_id": job_id,
        }


# ============================================================
# Outbox Publisher
# ============================================================


@shared_task(
    name=("nexusflow.workers.tasks.publish_outbox_events"),
)
def publish_outbox_events() -> dict[str, int]:
    published = 0

    with SessionLocal.begin() as session:
        events = session.scalars(
            select(OutboxEvent)
            .where(OutboxEvent.status == OutboxStatus.PENDING)
            .order_by(OutboxEvent.created_at)
            .with_for_update(skip_locked=True)
            .limit(settings.outbox_batch_size)
        ).all()

        for event in events:
            # --------------------------------------------------
            # Job must still exist.
            # --------------------------------------------------

            job = session.scalar(select(Job).where(Job.id == event.aggregate_id).with_for_update())

            if job is None:
                # There is nothing left to dispatch.
                event.status = OutboxStatus.PUBLISHED

                event.published_at = datetime.now(timezone.utc)

                continue

            # --------------------------------------------------
            # Put job into queue state before dispatch.
            # --------------------------------------------------

            if job.status == JobStatus.PENDING:
                job.status = JobStatus.QUEUED

            # --------------------------------------------------
            # Publish to Celery/RabbitMQ.
            #
            # RabbitMQ quorum publishing uses confirmation.
            # --------------------------------------------------

            execute_job.delay(str(job.id))

            event.status = OutboxStatus.PUBLISHED

            event.published_at = datetime.now(timezone.utc)

            published += 1

    return {
        "published": published,
    }
