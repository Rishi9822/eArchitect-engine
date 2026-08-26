"""
API v1 routes for the eArchitect Geometry Engine.

Endpoints:
    POST /api/v1/layouts/generate  — generate floor plan layout(s)
    GET  /api/v1/health            — health check
    GET  /api/v1/version           — engine version info

Backward compatibility:
    POST /generate-layout          — alias for v1 generate
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..config import ENGINE_VERSION, ENGINE_NAME
from ..models.input_models import GenerateLayoutRequest
from ..services.layout_service import generate_layout_response
from .errors import EngineError

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# V1 ROUTER
# ─────────────────────────────────────────────

v1_router = APIRouter(prefix="/api/v1", tags=["v1"])


@v1_router.get("/health", tags=["health"])
def health_v1():
    """Health check endpoint."""
    return {"status": "healthy", "service": ENGINE_NAME}


@v1_router.get("/version", tags=["health"])
def version_v1():
    """Engine version information."""
    return {
        "service": ENGINE_NAME,
        "version": ENGINE_VERSION,
        "api_version": "v1",
    }


@v1_router.post(
    "/layouts/generate",
    tags=["layout"],
    summary="Generate floor plan layout using BSP",
    description=(
        "Accepts an irregular plot polygon, room requirements, entrance config, "
        "and user preferences.  Returns validated architectural floor-plan geometry "
        "with measurements, quality scores, and candidate ranking."
    ),
)
def generate_layout_v1(request: GenerateLayoutRequest):
    """Generate one or more layout candidates."""
    try:
        return generate_layout_response(request)
    except EngineError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_response(),
        )
    except Exception as exc:
        logger.exception("Unhandled error in layout generation")
        return JSONResponse(
            status_code=500,
            content={
                "error_code": "INTERNAL_ERROR",
                "message": f"Geometry engine error: {str(exc)}",
                "details": {},
            },
        )


# ─────────────────────────────────────────────
# BACKWARD-COMPATIBLE ROUTER
# ─────────────────────────────────────────────

compat_router = APIRouter(tags=["layout-compat"])


@compat_router.post(
    "/generate-layout",
    tags=["layout"],
    summary="Generate floor plan layout (backward-compatible)",
    description="Backward-compatible alias for POST /api/v1/layouts/generate",
)
def generate_layout_compat(request: GenerateLayoutRequest):
    """Backward-compatible endpoint — delegates to v1."""
    return generate_layout_v1(request)
