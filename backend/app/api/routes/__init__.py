"""API route modules."""

from fastapi import APIRouter

from app.api.routes import auth, health, menu, restaurants

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(menu.router, tags=["menu"])
api_router.include_router(restaurants.router, tags=["restaurants"])
