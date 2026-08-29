"""
Pydantic output models for the eArchitect Geometry Engine API v1.

All geometry in metres.  Areas provided in both sqm and sqft.
"""
from __future__ import annotations

from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field

from .common import Coordinate


# ─────────────────────────────────────────────
# LAYOUT METADATA
# ─────────────────────────────────────────────

class LayoutMetadata(BaseModel):
    """Top-level identifiers for a generated layout."""
    id: str
    version: str = "1.0"
    engine_version: str
    units: str = "metric"
    generation_time_ms: float = 0.0


# ─────────────────────────────────────────────
# PLOT & BUILDABLE AREA
# ─────────────────────────────────────────────

class PlotOutput(BaseModel):
    """Original plot boundary with area and orientation."""
    boundary: List[Coordinate]
    area_sqft: float
    area_sqm: float
    facing: str
    road_side: str


class BuildableAreaOutput(BaseModel):
    """Setback-applied buildable area."""
    boundary: List[Coordinate]
    area_sqft: float
    area_sqm: float
    setback_m: float


# ─────────────────────────────────────────────
# ROOMS
# ─────────────────────────────────────────────

class RoomOutput(BaseModel):
    """A generated room with geometry and metadata."""
    id: str
    type: str
    area_sqft: float
    area_sqm: float
    polygon: List[Coordinate]
    centroid: Coordinate
    aspect_ratio: float
    zone: Literal["public", "private", "service", "parking", "dead"]
    min_width_m: float = 0.0
    min_length_m: float = 0.0
    has_exterior_wall: bool = False
    has_window: bool = False


# ─────────────────────────────────────────────
# WALLS
# ─────────────────────────────────────────────

class WallSegment(BaseModel):
    """A classified wall segment with room relationships."""
    id: str
    start: Coordinate
    end: Coordinate
    type: Literal["exterior", "interior"]
    thickness: float = Field(description="Wall thickness in metres")
    length: float
    orientation: str = ""          # "horizontal", "vertical", "diagonal"
    bearing_deg: float = 0.0       # degrees from north (0-360)
    room_a: Optional[str] = None   # Room ID on one side
    room_b: Optional[str] = None   # Room ID on other side (null for exterior)


# ─────────────────────────────────────────────
# DOORS
# ─────────────────────────────────────────────

class DoorOutput(BaseModel):
    """An internal or entrance door."""
    id: str
    type: Literal["main_entrance", "internal", "service"]
    width: float
    position: Coordinate
    wall_id: Optional[str] = None
    from_room: Optional[str] = None
    to_room: Optional[str] = None


# ─────────────────────────────────────────────
# WINDOWS
# ─────────────────────────────────────────────

class WindowOutput(BaseModel):
    """A window placed on an exterior wall."""
    id: str
    room_id: str
    wall_id: Optional[str] = None
    position: Coordinate
    width: float
    type: Literal["standard", "ventilation", "picture"]
    sill_height_m: float = 0.9
    orientation: str = ""


# ─────────────────────────────────────────────
# ENTRANCES
# ─────────────────────────────────────────────

class EntranceOutput(BaseModel):
    """Main entrance entity."""
    id: str
    type: str = "main"
    side: str
    position: Coordinate
    width: float
    wall_id: Optional[str] = None
    room_id: Optional[str] = None
    direction: str = ""


# ─────────────────────────────────────────────
# PARKING
# ─────────────────────────────────────────────

class ParkingOutput(BaseModel):
    """Parking entity with dimensional constraints."""
    id: str
    room_id: str
    polygon: List[Coordinate]
    vehicle_type: str = "car"
    width_m: float
    length_m: float
    area_sqft: float
    area_sqm: float
    road_access: bool = False
    meets_minimum: bool = True


# ─────────────────────────────────────────────
# CORRIDORS
# ─────────────────────────────────────────────

class CorridorOutput(BaseModel):
    """A first-class corridor/circulation element."""
    id: str
    type: str = "corridor"
    polygon: List[Coordinate]
    centroid: Optional[Coordinate] = None
    area_sqm: float = 0.0
    width: float = 0.0
    length: float = 0.0
    connected_rooms: List[str] = Field(default_factory=list)
    entrance_connection: bool = False


# ─────────────────────────────────────────────
# DEAD SPACES
# ─────────────────────────────────────────────

class DeadSpaceOutput(BaseModel):
    """Leftover polygon classified by potential use."""
    id: str
    polygon: List[Coordinate]
    area_sqft: float
    area_sqm: float
    classification: Literal["storage", "passage", "utility", "unusable"]


# ─────────────────────────────────────────────
# CIRCULATION
# ─────────────────────────────────────────────

class CirculationOutput(BaseModel):
    """Room connectivity analysis."""
    connected: bool = False
    reachable_rooms: int = 0
    total_rooms: int = 0
    dead_ends: int = 0
    graph_edges: int = 0
    score: float = 0.0


# ─────────────────────────────────────────────
# MEASUREMENTS
# ─────────────────────────────────────────────

class MeasurementsOutput(BaseModel):
    """
    Estimator-ready geometric measurements.

    The Platform's estimator module will consume these values.
    NO material prices or cost calculations here.
    """
    plot_area_sqm: float = 0.0
    plot_area_sqft: float = 0.0
    buildable_area_sqm: float = 0.0
    buildable_area_sqft: float = 0.0
    room_area_sqm: float = 0.0
    room_area_sqft: float = 0.0
    built_up_area_sqm: float = 0.0
    built_up_area_sqft: float = 0.0
    exterior_wall_length_m: float = 0.0
    interior_wall_length_m: float = 0.0
    total_wall_length_m: float = 0.0
    exterior_wall_area_sqm: float = 0.0
    interior_wall_area_sqm: float = 0.0
    floor_area_sqm: float = 0.0
    floor_area_sqft: float = 0.0
    roof_area_sqm: float = 0.0
    roof_area_sqft: float = 0.0
    total_door_count: int = 0
    total_window_count: int = 0
    perimeter_m: float = 0.0
    corridor_area_sqm: float = 0.0
    corridor_area_sqft: float = 0.0


# ─────────────────────────────────────────────
# METRICS
# ─────────────────────────────────────────────

class MetricsOutput(BaseModel):
    """Distinct architectural metrics — not to be confused with scores."""
    building_coverage: float = 0.0               # built-up / plot area
    building_coverage_percentage: float = 0.0
    buildable_utilization: float = 0.0            # room area / buildable area
    buildable_utilization_percentage: float = 0.0
    dead_space_area_sqm: float = 0.0
    dead_space_area_sqft: float = 0.0
    dead_space_percentage: float = 0.0


# ─────────────────────────────────────────────
# SCORE
# ─────────────────────────────────────────────

class ScoreBreakdown(BaseModel):
    """Detailed quality score breakdown."""
    buildable_utilization: float = 0.0
    building_coverage: float = 0.0
    aspect_quality: float = 0.0
    adjacency: float = 0.0
    circulation: float = 0.0
    natural_light: float = 0.0
    ventilation: float = 0.0
    parking_accessibility: float = 0.0
    dead_space_efficiency: float = 0.0
    constraint_compliance: float = 0.0
    overall: float = 0.0


# ─────────────────────────────────────────────
# VALIDATION
# ─────────────────────────────────────────────

class ValidationItem(BaseModel):
    """A single validation warning or error."""
    code: str
    severity: Literal["warning", "error"]
    message: str
    details: Optional[Dict[str, Any]] = None


class ValidationOutput(BaseModel):
    """Validation summary for a layout candidate."""
    valid: bool = True
    warnings: List[ValidationItem] = Field(default_factory=list)
    errors: List[ValidationItem] = Field(default_factory=list)
    constraints_checked: List[str] = Field(default_factory=list)


# ─────────────────────────────────────────────
# CANDIDATE
# ─────────────────────────────────────────────

class CandidateLayout(BaseModel):
    """A single candidate layout with all data."""
    id: str
    strategy: str
    rooms: List[RoomOutput]
    walls: List[WallSegment]
    doors: List[DoorOutput]
    windows: List[WindowOutput]
    entrances: List[EntranceOutput]
    parking: List[ParkingOutput]
    dead_spaces: List[DeadSpaceOutput]
    circulation: CirculationOutput
    measurements: MeasurementsOutput
    metrics: MetricsOutput
    score: ScoreBreakdown
    validation: ValidationOutput
    corridors: List[CorridorOutput] = Field(default_factory=list)


# ─────────────────────────────────────────────
# TOP-LEVEL RESPONSE
# ─────────────────────────────────────────────

class LayoutResponse(BaseModel):
    """
    Top-level API response for POST /api/v1/layouts/generate.

    Contains the plot/buildable boundaries, all candidates,
    and a pointer to the best one.
    """
    layout: LayoutMetadata
    plot: PlotOutput
    buildable_area: BuildableAreaOutput
    candidates: List[CandidateLayout]
    best_candidate_id: str

    # Timing breakdown (milliseconds)
    timing: Optional[Dict[str, float]] = None


# ─────────────────────────────────────────────
# ERROR RESPONSE
# ─────────────────────────────────────────────

class EngineErrorResponse(BaseModel):
    """Structured error response."""
    error_code: str
    message: str
    details: Optional[Dict[str, Any]] = None
