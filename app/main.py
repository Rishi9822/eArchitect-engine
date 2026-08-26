"""
FastAPI entrypoint for the eArchitect Geometry Engine v2.

Runs on: http://localhost:8000

API endpoints:
    POST /api/v1/layouts/generate   — generate floor plan layout(s)
    GET  /api/v1/health             — health check
    GET  /api/v1/version            — engine version
    POST /generate-layout           — backward-compatible alias
"""
from __future__ import annotations

import logging

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import ENGINE_NAME, ENGINE_VERSION, LOG_LEVEL, get_allowed_origins
from .api.routes import v1_router, compat_router
from .api.errors import EngineError, engine_error_handler

# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# APPLICATION FACTORY
# ─────────────────────────────────────────────

app = FastAPI(
    title=ENGINE_NAME,
    description=(
        "Computational geometry backend for AI-Based Automated Floor Plan Generation. "
        "Implements Recursive Binary Space Partitioning (BSP) to generate "
        "architectural floor plans from irregular plot polygons. "
        "Returns validated geometry, measurements, and quality scores. "
        "NO frontend UI, NO material pricing, NO estimator logic."
    ),
    version=ENGINE_VERSION,
)

# ─────────────────────────────────────────────
# CORS
# ─────────────────────────────────────────────

origins = get_allowed_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
# ERROR HANDLER
# ─────────────────────────────────────────────

app.add_exception_handler(EngineError, engine_error_handler)

# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────

# Root health check (Docker compatibility)
@app.get("/", tags=["health"])
def root():
    return {"status": "ok", "service": ENGINE_NAME, "version": ENGINE_VERSION}


@app.get("/health", tags=["health"])
def health():
    return {"status": "healthy"}


# Register versioned and backward-compatible routers
app.include_router(v1_router)
app.include_router(compat_router)

logger.info("%s v%s started", ENGINE_NAME, ENGINE_VERSION)

# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
