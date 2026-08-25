"""
Pydantic models for input validation and structured output.
All geometry uses (x, y) tuples in meters.
"""
from __future__ import annotations

from typing import List, Optional, Literal
from pydantic import BaseModel, Field, model_validator


# ─────────────────────────────────────────────
# INPUT MODELS
# ─────────────────────────────────────────────

class Point(BaseModel):
    x: float
    y: float


class PlotInput(BaseModel):
    points: List[Point] = Field(..., min_length=3)
    facing: Literal["north", "south", "east", "west"] = "north"
    road_side: Literal["front", "back", "left", "right"] = "front"
    setback: float = Field(3.0, ge=0.0, description="Setback distance in meters")

    @model_validator(mode="after")
    def at_least_three_distinct_points(self) -> "PlotInput":
        pts = [(p.x, p.y) for p in self.points]
        if len(set(pts)) < 3:
            raise ValueError("Plot must have at least 3 distinct points")
        return self


class RoomRequirement(BaseModel):
    type: str = Field(..., description="Room type, e.g. bedroom, kitchen, living")
    count: int = Field(..., ge=1)
    min_area: float = Field(..., gt=0, description="Minimum area in sq ft")
    priority: Optional[int] = Field(None, description="Placement priority (lower = higher priority)")


class EntranceInput(BaseModel):
    side: Literal["front", "back", "left", "right"] = "front"
    width: float = Field(5.0, gt=0)


class PreferencesInput(BaseModel):
    parking: bool = False
    ventilation_priority: bool = False
    natural_light_priority: bool = False


class GenerateLayoutRequest(BaseModel):
    plot: PlotInput
    rooms: List[RoomRequirement] = Field(..., min_length=1)
    entrance: EntranceInput
    preferences: Optional[PreferencesInput] = Field(default_factory=PreferencesInput)


# ─────────────────────────────────────────────
# OUTPUT MODELS
# ─────────────────────────────────────────────

class Coordinate(BaseModel):
    x: float
    y: float


class RoomOutput(BaseModel):
    id: str
    type: str
    area_sqft: float
    area_sqm: float
    polygon: List[Coordinate]
    centroid: Coordinate
    aspect_ratio: float
    zone: Literal["public", "private", "service", "parking", "dead"]


class WallSegment(BaseModel):
    start: Coordinate
    end: Coordinate
    type: Literal["exterior", "interior"]
    thickness: float = Field(description="Wall thickness in meters")
    length: float


class DeadSpaceOutput(BaseModel):
    polygon: List[Coordinate]
    area_sqft: float
    classification: Literal["storage", "passage", "utility", "unusable"]


class ScoreBreakdown(BaseModel):
    space_utilization: float
    aspect_ratio_quality: float
    adjacency_correctness: float
    circulation_efficiency: float
    overall: float


class LayoutResponse(BaseModel):
    rooms: List[RoomOutput]
    walls: List[WallSegment]
    dead_spaces: List[DeadSpaceOutput]
    score: float
    score_breakdown: ScoreBreakdown
    plot_area_sqft: float
    used_area_sqft: float
    setback_applied: float
