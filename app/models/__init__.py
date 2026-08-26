"""
Models package — re-exports for convenient import.
"""
from .common import Coordinate, Point
from .input_models import (
    PlotInput,
    RoomRequirement,
    EntranceInput,
    PreferencesInput,
    GenerateLayoutRequest,
)
from .output_models import (
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
    "CirculationOutput", "MeasurementsOutput", "MetricsOutput",
    "ScoreBreakdown", "ValidationItem", "ValidationOutput",
    "CandidateLayout", "LayoutResponse", "EngineErrorResponse",
]
