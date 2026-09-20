from fastapi import APIRouter

from nexusflow.api.v1 import auth, health, jobs, tenants


api_router = APIRouter()

api_router.include_router(
    health.router,
    prefix="/health",
    tags=["health"],
)

api_router.include_router(
    auth.router,
    prefix="/auth",
    tags=["auth"],
)

api_router.include_router(
    tenants.router,
    prefix="/tenants",
    tags=["tenants"],
)

api_router.include_router(
    jobs.router,
    prefix="/jobs",
    tags=["jobs"],
)