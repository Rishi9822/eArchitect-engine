"""
Backward-compatibility bridge for models.
Re-exports from app.models.*
"""
from .models.common import Coordinate, Point
from .models.input_models import (
    PlotInput,
    RoomRequirement,
    EntranceInput,
    PreferencesInput,
    GenerateLayoutRequest,
)
from .models.output_models import (
    LayoutMetadata,
    PlotOutput,
    BuildableAreaOutput,
    RoomOutput,
    WallSegment,
    DoorOutput,
    WindowOutput,
    EntranceOutput,
    ParkingOutput,
    DeadSpaceOutput,
    CirculationOutput,
    CirculationBreakdown,
    MeasurementsOutput,
    MetricsOutput,
    ScoreBreakdown,
    ValidationItem,
    ValidationOutput,
    CandidateLayout,
    LayoutResponse,
    EngineErrorResponse,
)

__all__ = [
    "Coordinate", "Point",
    "PlotInput", "RoomRequirement", "EntranceInput", "PreferencesInput",
    "GenerateLayoutRequest",
    "LayoutMetadata", "PlotOutput", "BuildableAreaOutput",
    "RoomOutput", "WallSegment", "DoorOutput", "WindowOutput",
    "EntranceOutput", "ParkingOutput", "DeadSpaceOutput",
    "CirculationOutput", "CirculationBreakdown", "MeasurementsOutput", "MetricsOutput",
    "ScoreBreakdown", "ValidationItem", "ValidationOutput",
    "CandidateLayout", "LayoutResponse", "EngineErrorResponse",
]
