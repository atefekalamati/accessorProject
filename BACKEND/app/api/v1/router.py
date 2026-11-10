from fastapi import APIRouter

from app.modules.addresses.router import router as addresses_router
from app.modules.admin.audit_logs import router as admin_audit_router
from app.modules.admin.customers import router as admin_customers_router
from app.modules.admin.router import router as admin_users_router
from app.modules.auth.router import router as auth_router
from app.modules.auth.router import users_router
from app.modules.cart.router import router as cart_router
from app.modules.catalog.admin_product_router import router as admin_products_router
from app.modules.catalog.admin_router import router as admin_categories_router
from app.modules.catalog.router import products_router
from app.modules.catalog.router import router as categories_router
from app.modules.checkout.router import router as checkout_router
from app.modules.content.router import (
    admin_faq_router,
    admin_pages_router,
    faq_router,
    pages_router,
)
from app.modules.discounts.admin_router import router as admin_discounts_router
from app.modules.inventory.admin_router import router as admin_inventory_router
from app.modules.media.router import router as admin_media_router
from app.modules.orders.admin_router import orders_router as admin_orders_router
from app.modules.orders.admin_router import payments_router as admin_payments_router
from app.modules.orders.router import router as orders_router
from app.modules.payments.router import router as payments_router
from app.modules.pricing.router import prices_router as admin_prices_router
from app.modules.pricing.router import router as admin_pricing_router
from app.modules.reports.router import dashboard_router as admin_dashboard_router
from app.modules.reports.router import reports_router as admin_reports_router
from app.modules.shipping.admin_router import router as admin_shipping_router
from app.modules.shipping.router import router as shipping_router
from app.shared.database.router import readiness_router
from app.shared.health.router import router as health_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(readiness_router)
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(admin_users_router)
api_router.include_router(admin_customers_router)
api_router.include_router(admin_audit_router)
api_router.include_router(admin_dashboard_router)
api_router.include_router(admin_reports_router)
api_router.include_router(categories_router)
api_router.include_router(products_router)
api_router.include_router(admin_categories_router)
api_router.include_router(admin_products_router)
api_router.include_router(admin_media_router)
api_router.include_router(admin_pricing_router)
api_router.include_router(admin_prices_router)
api_router.include_router(admin_inventory_router)
api_router.include_router(cart_router)
api_router.include_router(admin_discounts_router)
api_router.include_router(addresses_router)
api_router.include_router(shipping_router)
api_router.include_router(admin_shipping_router)
api_router.include_router(checkout_router)
api_router.include_router(orders_router)
api_router.include_router(admin_orders_router)
api_router.include_router(admin_payments_router)
api_router.include_router(payments_router)
api_router.include_router(pages_router)
api_router.include_router(admin_pages_router)
api_router.include_router(faq_router)
api_router.include_router(admin_faq_router)
