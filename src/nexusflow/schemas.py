from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from nexusflow.models import JobStatus


# ============================================================
# Authentication
# ============================================================


class UserRegister(BaseModel):
    email: EmailStr

    password: str = Field(
        min_length=8,
        max_length=128,
    )

    organization_name: str = Field(
        min_length=2,
        max_length=200,
    )


class UserLogin(BaseModel):
    email: EmailStr

    password: str = Field(
        min_length=1,
        max_length=128,
    )


class TokenResponse(BaseModel):
    access_token: str

    token_type: str = "bearer"


class UserRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID

    email: str

    is_active: bool


# ============================================================
# Organization
# ============================================================


class OrganizationRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID

    name: str

    slug: str


# ============================================================
# Jobs
# ============================================================


class JobCreate(BaseModel):
    job_type: str = Field(
        min_length=1,
        max_length=100,
    )

    payload: dict[str, Any] = Field(
        default_factory=dict,
    )


class JobRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID

    organization_id: uuid.UUID

    created_by: uuid.UUID

    job_type: str

    status: JobStatus

    payload: dict[str, Any]

    result: dict[str, Any] | None

    error: str | None

    created_at: datetime

    updated_at: datetime


class JobListResponse(BaseModel):
    items: list[JobRead]

    next_cursor: str | None = None


# ============================================================
# Health
# ============================================================


class HealthResponse(BaseModel):
    status: str

    database: str

    redis: str