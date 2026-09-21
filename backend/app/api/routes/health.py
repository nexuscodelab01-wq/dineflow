"""Health check endpoints."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


class HealthResponse(BaseModel):
    status: str


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/health/ready")
def readiness(db: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
    """Readiness probe: is the app able to serve traffic (i.e. can it reach the database)?"""
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 — any failure means "not ready"
        logger.error("Readiness check failed: %s", exc)
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return {"status": "ready", "database": "ok"}
