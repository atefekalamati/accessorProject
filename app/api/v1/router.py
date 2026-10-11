from fastapi import APIRouter

from app.modules.admin.router import router as admin_users_router
from app.modules.auth.router import router as auth_router
from app.modules.auth.router import users_router
from app.modules.catalog.admin_product_router import router as admin_products_router
from app.modules.catalog.admin_router import router as admin_categories_router
from app.modules.catalog.router import router as categories_router
from app.modules.media.router import router as admin_media_router
from app.shared.database.router import readiness_router
from app.shared.health.router import router as health_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(readiness_router)
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(admin_users_router)
api_router.include_router(categories_router)
api_router.include_router(admin_categories_router)
api_router.include_router(admin_products_router)
api_router.include_router(admin_media_router)
