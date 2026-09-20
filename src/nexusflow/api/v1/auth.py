import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nexusflow.db import get_db
from nexusflow.dependencies import CurrentUser
from nexusflow.models import Membership, Organization, User
from nexusflow.schemas import (
    TokenResponse,
    UserLogin,
    UserRead,
    UserRegister,
)
from nexusflow.security import (
    create_access_token,
    hash_password,
    verify_password,
)


router = APIRouter()


def make_slug(value: str) -> str:
    slug = value.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: UserRegister,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    email = payload.email.lower().strip()

    existing = await db.scalar(
        select(User).where(User.email == email)
    )

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    organization = Organization(
        name=payload.organization_name.strip(),
        slug=f"{make_slug(payload.organization_name)}-{uuid.uuid4().hex[:8]}",
    )

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
    )

    db.add(organization)
    db.add(user)

    await db.flush()

    membership = Membership(
        user_id=user.id,
        organization_id=organization.id,
        role="owner",
    )

    db.add(membership)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Unable to create account",
        ) from exc

    token = create_access_token(
        user_id=str(user.id),
        organization_id=str(organization.id),
        role="owner",
    )

    return TokenResponse(access_token=token)


@router.post(
    "/login",
    response_model=TokenResponse,
)
async def login(
    payload: UserLogin,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    email = payload.email.lower().strip()

    user = await db.scalar(
        select(User).where(User.email == email)
    )

    if user is None or not verify_password(
        payload.password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    membership = await db.scalar(
        select(Membership)
        .where(Membership.user_id == user.id)
        .limit(1)
    )

    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has no organization membership",
        )

    token = create_access_token(
        user_id=str(user.id),
        organization_id=str(membership.organization_id),
        role=membership.role,
    )

    return TokenResponse(access_token=token)


@router.get(
    "/me",
    response_model=UserRead,
)
async def me(
    current_user: CurrentUser,
) -> UserRead:
    return UserRead.model_validate(current_user)