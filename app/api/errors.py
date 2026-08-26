"""
Structured error handling for the eArchitect Geometry Engine.

Defines error codes, error response model, and exception classes.
"""
from __future__ import annotations

from typing import Optional, Dict, Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse


# ─────────────────────────────────────────────
# ERROR CODES
# ─────────────────────────────────────────────

class EngineError(Exception):
    """Base exception for geometry engine errors."""
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 422,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)

    def to_response(self) -> dict:
        return {
            "error_code": self.code,
            "message": self.message,
            "details": self.details,
        }


class InvalidPlotError(EngineError):
    def __init__(self, message: str, **details):
        super().__init__("INVALID_PLOT", message, 422, details)


class InvalidSetbackError(EngineError):
    def __init__(self, message: str, **details):
        super().__init__("INVALID_SETBACK", message, 422, details)


class NoBuildableAreaError(EngineError):
    def __init__(self, message: str, **details):
        super().__init__("NO_BUILDABLE_AREA", message, 422, details)


class RoomRequirementError(EngineError):
    def __init__(self, message: str, **details):
        super().__init__("ROOM_REQUIREMENT_INVALID", message, 422, details)


class LayoutInfeasibleError(EngineError):
    def __init__(self, message: str, **details):
        super().__init__("LAYOUT_INFEASIBLE", message, 422, details)


class GeometryError(EngineError):
    def __init__(self, message: str, **details):
        super().__init__("GEOMETRY_INVALID", message, 500, details)


# ─────────────────────────────────────────────
# FASTAPI ERROR HANDLER
# ─────────────────────────────────────────────

def engine_error_handler(exc: EngineError) -> JSONResponse:
    """Convert an EngineError to a structured JSON response."""
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_response(),
    )
