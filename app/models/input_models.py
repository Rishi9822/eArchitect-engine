"""
Pydantic input models for the eArchitect Geometry Engine API.

All polygon coordinates in METRES.
Room area requirements accepted in sq-ft (converted internally).
"""
from __future__ import annotations

from typing import List, Optional, Literal
from pydantic import BaseModel, Field, model_validator

from .common import Point


# ─────────────────────────────────────────────
# PLOT INPUT
# ─────────────────────────────────────────────

class PlotInput(BaseModel):
    """Plot polygon with orientation and setback."""
    points: List[Point] = Field(..., min_length=3)
    facing: Literal["north", "south", "east", "west"] = "north"
    road_side: Literal["front", "back", "left", "right"] = "front"
    setback: float = Field(3.0, ge=0.0, description="Setback distance in metres")

    @model_validator(mode="after")
    def at_least_three_distinct_points(self) -> "PlotInput":
        pts = [(p.x, p.y) for p in self.points]
        if len(set(pts)) < 3:
            raise ValueError("Plot must have at least 3 distinct points")
        return self


# ─────────────────────────────────────────────
# ROOM REQUIREMENT
# ─────────────────────────────────────────────

class RoomRequirement(BaseModel):
    """
    Specification for one room type.

    All area/dimension fields use sq-ft / feet.
    The engine converts to metric internally.
    """
    type: str = Field(..., description="Room type, e.g. bedroom, kitchen, living")
    count: int = Field(..., ge=1)
    min_area: float = Field(..., gt=0, description="Minimum area in sq ft")
    min_width: Optional[float] = Field(None, gt=0, description="Minimum width in feet")
    min_length: Optional[float] = Field(None, gt=0, description="Minimum length in feet")
    preferred_aspect_ratio: Optional[float] = Field(
        None, gt=0, description="Preferred max aspect ratio (e.g. 2.0)"
    )
    priority: Optional[int] = Field(
        None, description="Placement priority (lower = higher priority)"
    )
    zone: Optional[str] = Field(
        None, description="Override zone (public/private/service/parking)"
    )
    adjacency_preferred: Optional[List[str]] = Field(
        None, description="Room types this room should be near"
    )
    adjacency_avoid: Optional[List[str]] = Field(
        None, description="Room types this room should avoid"
    )
    exterior_wall_required: Optional[bool] = Field(
        None, description="Whether this room requires an exterior wall"
    )


# ─────────────────────────────────────────────
# ENTRANCE INPUT
# ─────────────────────────────────────────────

class EntranceInput(BaseModel):
    """Main entrance specification."""
    side: Literal["front", "back", "left", "right"] = "front"
    width: float = Field(1.2, gt=0, description="Entrance width in metres")


# ─────────────────────────────────────────────
# PREFERENCES INPUT
# ─────────────────────────────────────────────

class PreferencesInput(BaseModel):
    """User preferences that influence layout generation and scoring."""
    parking: bool = False
    ventilation_priority: bool = False
    natural_light_priority: bool = False


# ─────────────────────────────────────────────
# TOP-LEVEL REQUEST
# ─────────────────────────────────────────────

class GenerateLayoutRequest(BaseModel):
    """
    Top-level request body for POST /api/v1/layouts/generate.
    """
    plot: PlotInput
    rooms: List[RoomRequirement] = Field(..., min_length=1)
    entrance: EntranceInput = Field(default_factory=EntranceInput)
    preferences: Optional[PreferencesInput] = Field(default_factory=PreferencesInput)
    candidate_count: int = Field(1, ge=1, le=10, description="Number of layout candidates")
    seed: Optional[int] = Field(None, description="Random seed for deterministic generation")
