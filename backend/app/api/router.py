"""API router aggregation."""
from fastapi import APIRouter

from app.api.routes import analytics, health, navigation, realtime, simulation

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(simulation.router)
api_router.include_router(navigation.router)
api_router.include_router(analytics.router)
api_router.include_router(realtime.router)
