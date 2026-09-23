from fastapi import APIRouter

from app.api.address_book import router as address_book_router
from app.api.export import router as export_router
from app.api.gateway_webhook import router as gateway_webhook_router
from app.api.inventory import router as inventory_router
from app.api.orders import router as orders_router
from app.api.payment import router as payment_router
from app.api.pdpa import router as pdpa_router
from app.api.verification import router as verification_router
from app.api.webhook import router as webhook_router

api_router = APIRouter()
api_router.include_router(inventory_router)
api_router.include_router(orders_router)
api_router.include_router(address_book_router)
api_router.include_router(payment_router)
api_router.include_router(verification_router)
api_router.include_router(webhook_router)
api_router.include_router(gateway_webhook_router)
api_router.include_router(pdpa_router)
api_router.include_router(export_router)
