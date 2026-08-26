"""
Hard and soft constraint definitions for layout validation.

Separates HARD constraints (must satisfy) from SOFT preferences
(affect scoring only).
"""
from __future__ import annotations

import logging
from typing import List, Dict
from dataclasses import dataclass

from shapely.geometry import Polygon

from ..config import SQ_M_TO_SQ_FT
from .bsp import RoomSpec

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# FEASIBILITY CHECK (pre-generation)
# ─────────────────────────────────────────────

@dataclass
class FeasibilityResult:
    """Result of a pre-generation feasibility check."""
    feasible: bool = True
    required_area_sqm: float = 0.0
    available_area_sqm: float = 0.0
    required_rooms: int = 0
    messages: List[str] = None

    def __post_init__(self):
        if self.messages is None:
            self.messages = []


def check_feasibility(
    specs: List[RoomSpec],
    buildable_polygon: Polygon,
) -> FeasibilityResult:
    """
    Pre-generation feasibility check.

    Verifies that the total minimum room area can fit within
    the buildable polygon, with a margin for walls/circulation.
    """
    available = buildable_polygon.area
    required = sum(s.min_area_sqm for s in specs)

    # Assume ~10% overhead for walls and circulation
    usable = available * 0.90

    result = FeasibilityResult(
        required_area_sqm=required,
        available_area_sqm=available,
        required_rooms=len(specs),
    )

    if required > usable:
        result.feasible = False
        result.messages.append(
            f"Total required area ({required * SQ_M_TO_SQ_FT:.0f} sqft) exceeds "
            f"available buildable area ({usable * SQ_M_TO_SQ_FT:.0f} sqft after wall overhead). "
            f"Reduce room requirements or setback."
        )

    # Check if any single room is larger than buildable area
    for spec in specs:
        if spec.min_area_sqm > available:
            result.feasible = False
            result.messages.append(
                f"Room '{spec.id}' ({spec.type}) requires "
                f"{spec.min_area_sqm * SQ_M_TO_SQ_FT:.0f} sqft but total "
                f"buildable area is only {available * SQ_M_TO_SQ_FT:.0f} sqft"
            )

    return result


# ─────────────────────────────────────────────
# CONSTRAINT DEFINITIONS
# ─────────────────────────────────────────────

HARD_CONSTRAINTS = [
    "ROOM_COMPLETENESS",       # All requested rooms must be placed
    "ROOM_AREA_MINIMUM",       # Each room must meet min area (within tolerance)
    "ROOM_NO_OVERLAP",         # No two rooms may overlap interiors
    "ROOM_VALID_GEOMETRY",     # All room polygons must be valid
    "ROOM_INSIDE_BOUNDARY",    # All rooms must be inside buildable area
]

SOFT_PREFERENCES = [
    "ROOM_DIMENSION_MINIMUM",  # Room min width/length
    "ROOM_ASPECT_RATIO",       # Room shape quality
    "ADJACENCY_PREFERRED",     # Room-level adjacency
    "ADJACENCY_AVOID",         # Room-level anti-adjacency
    "NATURAL_LIGHT",           # Exterior wall for light-needing rooms
    "VENTILATION",             # Window for ventilation
    "PARKING_DIMENSIONS",      # Parking min width/length
    "PARKING_ROAD_ACCESS",     # Parking near road side
]
