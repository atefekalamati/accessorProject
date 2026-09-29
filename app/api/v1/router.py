from fastapi import APIRouter

from app.shared.database.router import readiness_router
from app.shared.health.router import router as health_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(readiness_router)
