from fastapi import APIRouter

from app.modules.auth.router import router as auth_router
from app.modules.auth.router import users_router
from app.shared.database.router import readiness_router
from app.shared.health.router import router as health_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(readiness_router)
api_router.include_router(auth_router)
api_router.include_router(users_router)
