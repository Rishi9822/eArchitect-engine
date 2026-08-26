"""
Centralized configuration for the eArchitect Geometry Engine.

All architectural constants, environment-driven settings, and
room-type defaults live here.  No magic numbers should appear
anywhere else in the codebase.

Environment variables (all optional):
    ENGINE_ALLOWED_ORIGINS  — comma-separated list of CORS origins
    ENGINE_LOG_LEVEL        — logging level (default: INFO)
    ENGINE_VERSION          — semver string (default: 2.0.0)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# ─────────────────────────────────────────────
# UNIT CONVERSION
# ─────────────────────────────────────────────

SQ_FT_TO_SQ_M: float = 0.092903      # 1 sq ft in sq metres
SQ_M_TO_SQ_FT: float = 1.0 / SQ_FT_TO_SQ_M  # ~10.7639
FT_TO_M: float = 0.3048               # 1 foot in metres
M_TO_FT: float = 1.0 / FT_TO_M       # ~3.28084

# ─────────────────────────────────────────────
# ENGINE METADATA
# ─────────────────────────────────────────────

ENGINE_VERSION: str = os.getenv("ENGINE_VERSION", "2.0.0")
ENGINE_NAME: str = "eArchitect Geometry Engine"

# ─────────────────────────────────────────────
# CORS
# ─────────────────────────────────────────────

def get_allowed_origins() -> List[str]:
    raw = os.getenv("ENGINE_ALLOWED_ORIGINS", "*")
    if raw.strip() == "*":
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]

# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────

LOG_LEVEL: str = os.getenv("ENGINE_LOG_LEVEL", "INFO").upper()

# ─────────────────────────────────────────────
# WALL THICKNESSES (metres)
# ─────────────────────────────────────────────

EXTERIOR_WALL_THICKNESS: float = 0.2286   # 9 inches
INTERIOR_WALL_THICKNESS: float = 0.1143   # 4.5 inches

# ─────────────────────────────────────────────
# WALL EXTRACTION TOLERANCES
# ─────────────────────────────────────────────

SEGMENT_SNAP_TOLERANCE: float = 0.005     # 5 mm coordinate snap
MIN_WALL_LENGTH: float = 0.10             # Ignore wall segments < 10 cm
BOUNDARY_BUFFER: float = 0.05             # 5 cm buffer for boundary test
COLLINEAR_ANGLE_TOLERANCE: float = 2.0    # degrees — merge if bearing within this
COLLINEAR_GAP_TOLERANCE: float = 0.10     # metres — merge if gap < this

# ─────────────────────────────────────────────
# GEOMETRY TOLERANCES
# ─────────────────────────────────────────────

COORDINATE_SNAP: float = 0.001            # 1 mm snap for final output
MIN_POLYGON_AREA_SQM: float = 1.0         # Ignore polygon fragments < 1 sqm
DEAD_SPACE_MIN_AREA_SQM: float = 0.5      # Ignore dead space < 0.5 sqm

# ─────────────────────────────────────────────
# BSP PARAMETERS
# ─────────────────────────────────────────────

MAX_BSP_DEPTH: int = 12                   # Guard against infinite recursion
MAX_ASPECT_RATIO: float = 4.0             # Reject splits producing > 4:1 rooms
MIN_SPLIT_RATIO: float = 0.25             # Never split closer than 25% from edge
MAX_SPLIT_RATIO: float = 0.75
BSP_RATIO_SEARCH_STEP: float = 0.05       # Step size when searching for best ratio
BSP_AREA_TOLERANCE: float = 0.4           # Min fraction of required area for leaf

# ─────────────────────────────────────────────
# ZONE DEFINITIONS
# ─────────────────────────────────────────────

ZONE_MAP: Dict[str, str] = {
    "living": "public",
    "dining": "public",
    "foyer": "public",
    "lobby": "public",
    "bedroom": "private",
    "master_bedroom": "private",
    "study": "private",
    "dressing": "private",
    "kitchen": "service",
    "toilet": "service",
    "bathroom": "service",
    "utility": "service",
    "store": "service",
    "parking": "parking",
}

ZONE_ORDER: List[str] = ["public", "private", "service", "parking"]

ZONE_RATIOS: Dict[str, float] = {
    "public": 0.35,
    "private": 0.40,
    "service": 0.18,
    "parking": 0.07,
}

# ─────────────────────────────────────────────
# ROOM-TYPE DEFAULTS
# ─────────────────────────────────────────────

@dataclass
class RoomTypeDefaults:
    """Default constraints for a room type."""
    min_area_sqft: float = 80.0
    min_width_ft: float = 6.0
    min_length_ft: float = 8.0
    preferred_aspect_ratio: float = 2.0       # max preferred w:h
    max_aspect_ratio: float = 3.5
    requires_exterior_wall: bool = False
    requires_natural_light: bool = False
    requires_ventilation: bool = False
    default_door_width_m: float = 0.9
    default_window_width_m: float = 1.2
    window_sill_height_m: float = 0.9


ROOM_TYPE_DEFAULTS: Dict[str, RoomTypeDefaults] = {
    "living": RoomTypeDefaults(
        min_area_sqft=150, min_width_ft=10, min_length_ft=12,
        preferred_aspect_ratio=1.8, max_aspect_ratio=3.0,
        requires_exterior_wall=True, requires_natural_light=True,
        requires_ventilation=True,
        default_door_width_m=1.0, default_window_width_m=1.5,
    ),
    "dining": RoomTypeDefaults(
        min_area_sqft=100, min_width_ft=8, min_length_ft=10,
        preferred_aspect_ratio=1.8, max_aspect_ratio=3.0,
        requires_exterior_wall=True, requires_natural_light=True,
        requires_ventilation=True,
        default_door_width_m=0.9, default_window_width_m=1.2,
    ),
    "bedroom": RoomTypeDefaults(
        min_area_sqft=120, min_width_ft=10, min_length_ft=10,
        preferred_aspect_ratio=2.0, max_aspect_ratio=3.0,
        requires_exterior_wall=True, requires_natural_light=True,
        requires_ventilation=True,
        default_door_width_m=0.9, default_window_width_m=1.2,
    ),
    "master_bedroom": RoomTypeDefaults(
        min_area_sqft=180, min_width_ft=12, min_length_ft=12,
        preferred_aspect_ratio=1.8, max_aspect_ratio=2.5,
        requires_exterior_wall=True, requires_natural_light=True,
        requires_ventilation=True,
        default_door_width_m=1.0, default_window_width_m=1.5,
    ),
    "kitchen": RoomTypeDefaults(
        min_area_sqft=80, min_width_ft=7, min_length_ft=8,
        preferred_aspect_ratio=2.2, max_aspect_ratio=3.5,
        requires_exterior_wall=True, requires_natural_light=False,
        requires_ventilation=True,
        default_door_width_m=0.9, default_window_width_m=1.0,
    ),
    "toilet": RoomTypeDefaults(
        min_area_sqft=35, min_width_ft=4, min_length_ft=5,
        preferred_aspect_ratio=2.5, max_aspect_ratio=4.0,
        requires_exterior_wall=False, requires_natural_light=False,
        requires_ventilation=True,
        default_door_width_m=0.75, default_window_width_m=0.6,
        window_sill_height_m=1.5,
    ),
    "bathroom": RoomTypeDefaults(
        min_area_sqft=40, min_width_ft=5, min_length_ft=6,
        preferred_aspect_ratio=2.0, max_aspect_ratio=3.5,
        requires_exterior_wall=False, requires_natural_light=False,
        requires_ventilation=True,
        default_door_width_m=0.75, default_window_width_m=0.6,
        window_sill_height_m=1.5,
    ),
    "study": RoomTypeDefaults(
        min_area_sqft=80, min_width_ft=7, min_length_ft=8,
        preferred_aspect_ratio=2.0, max_aspect_ratio=3.0,
        requires_exterior_wall=True, requires_natural_light=True,
        requires_ventilation=True,
    ),
    "store": RoomTypeDefaults(
        min_area_sqft=30, min_width_ft=4, min_length_ft=5,
        preferred_aspect_ratio=3.0, max_aspect_ratio=4.0,
        requires_exterior_wall=False, requires_natural_light=False,
        requires_ventilation=False,
        default_door_width_m=0.75, default_window_width_m=0.0,
    ),
    "utility": RoomTypeDefaults(
        min_area_sqft=30, min_width_ft=4, min_length_ft=5,
        preferred_aspect_ratio=3.0, max_aspect_ratio=4.0,
        requires_exterior_wall=False, requires_natural_light=False,
        requires_ventilation=False,
        default_door_width_m=0.75, default_window_width_m=0.0,
    ),
}

def get_room_defaults(room_type: str) -> RoomTypeDefaults:
    """Return defaults for a room type, falling back to generic defaults."""
    return ROOM_TYPE_DEFAULTS.get(room_type.lower(), RoomTypeDefaults())

# ─────────────────────────────────────────────
# PARKING DEFAULTS
# ─────────────────────────────────────────────

PARKING_MIN_WIDTH_M: float = 2.5
PARKING_MIN_LENGTH_M: float = 5.0
PARKING_DEFAULT_AREA_SQM: float = 15.0      # ~161 sqft
PARKING_CLEARANCE_M: float = 0.5

# ─────────────────────────────────────────────
# DOOR DEFAULTS
# ─────────────────────────────────────────────

MAIN_ENTRANCE_WIDTH_M: float = 1.2
DEFAULT_DOOR_WIDTH_M: float = 0.9
MIN_WALL_FOR_DOOR_M: float = 1.2            # minimum wall length to place a door

# ─────────────────────────────────────────────
# WINDOW DEFAULTS
# ─────────────────────────────────────────────

DEFAULT_WINDOW_WIDTH_M: float = 1.2
MIN_WINDOW_WIDTH_M: float = 0.6
VENTILATION_WINDOW_WIDTH_M: float = 0.6      # small vent for toilet/bathroom
DEFAULT_SILL_HEIGHT_M: float = 0.9
MIN_WALL_FOR_WINDOW_M: float = 1.0           # minimum wall length to place a window

# ─────────────────────────────────────────────
# ADJACENCY RULES
# ─────────────────────────────────────────────

@dataclass
class AdjacencyRule:
    """Adjacency preference for a room type."""
    preferred: List[str] = field(default_factory=list)
    avoid: List[str] = field(default_factory=list)


ADJACENCY_RULES: Dict[str, AdjacencyRule] = {
    "living": AdjacencyRule(preferred=["dining", "kitchen", "foyer"]),
    "dining": AdjacencyRule(preferred=["living", "kitchen"]),
    "kitchen": AdjacencyRule(preferred=["dining", "utility", "store"]),
    "bedroom": AdjacencyRule(preferred=["bathroom", "toilet", "living"], avoid=["kitchen"]),
    "master_bedroom": AdjacencyRule(preferred=["bathroom", "dressing"], avoid=["kitchen"]),
    "toilet": AdjacencyRule(preferred=["bedroom", "living"], avoid=["dining", "kitchen"]),
    "bathroom": AdjacencyRule(preferred=["bedroom", "master_bedroom"], avoid=["dining", "kitchen"]),
    "parking": AdjacencyRule(preferred=["foyer", "living"], avoid=["bedroom"]),
    "study": AdjacencyRule(preferred=["bedroom", "living"]),
}

# Zone-level adjacency preferences (fallback)
PREFERRED_ZONE_ADJACENCY: List[tuple] = [
    ("public", "service"),
    ("public", "private"),
    ("private", "service"),
]

# ─────────────────────────────────────────────
# SCORING WEIGHTS
# ─────────────────────────────────────────────

SCORE_WEIGHTS: Dict[str, float] = {
    "buildable_utilization": 0.15,
    "building_coverage": 0.05,
    "aspect_quality": 0.15,
    "adjacency": 0.15,
    "circulation": 0.15,
    "natural_light": 0.10,
    "ventilation": 0.05,
    "parking_accessibility": 0.05,
    "dead_space_efficiency": 0.05,
    "constraint_compliance": 0.10,
}

# Dead space penalty weights
DEAD_SPACE_PENALTIES: Dict[str, float] = {
    "storage": 0.1,
    "passage": 0.05,
    "utility": 0.1,
    "unusable": 0.8,
}

# ─────────────────────────────────────────────
# CANDIDATE GENERATION
# ─────────────────────────────────────────────

DEFAULT_CANDIDATE_COUNT: int = 1
MAX_CANDIDATE_COUNT: int = 10

CANDIDATE_STRATEGIES: List[str] = ["balanced", "compact", "zoned"]

# ─────────────────────────────────────────────
# DEFAULT FLOOR HEIGHT (for wall area calc)
# ─────────────────────────────────────────────

DEFAULT_FLOOR_HEIGHT_M: float = 3.0          # 10 feet
