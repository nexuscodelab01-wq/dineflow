"""API route modules."""

from fastapi import APIRouter

from app.api.routes import admin, auth, health, loyalty, menu, orders, platform, realtime, reservations, restaurants, reviews, table_ordering, tenant

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(admin.router, tags=["admin"])
api_router.include_router(realtime.router, tags=["realtime"])
api_router.include_router(restaurants.router, tags=["restaurants"])
api_router.include_router(platform.router, tags=["platform"])
api_router.include_router(table_ordering.router, tags=["table ordering"])
api_router.include_router(tenant.router, tags=["tenant"])
api_router.include_router(menu.router, tags=["menu"])
api_router.include_router(orders.router, tags=["orders"])
api_router.include_router(reservations.router, tags=["reservations"])
api_router.include_router(reviews.router, tags=["reviews"])
api_router.include_router(loyalty.router, tags=["loyalty"])
