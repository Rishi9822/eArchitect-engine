"""
Hard and soft constraint definitions for layout validation.

Separates HARD constraints (must satisfy) from SOFT preferences
(affect scoring only).
"""
from __future__ import annotations

import logging
from typing import List, Dict, Optional, Set, Any, Tuple
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
    "CIRCULATION_CONNECTED",   # All rooms reachable from entrance via door graph
    "ENTRANCE_ROOM_TYPE",      # Entrance must be in eligible room type
    "NO_FORBIDDEN_DOORS",      # No forbidden door connections
    "HABITABLE_ROOM_WINDOW",   # Habitable room must have a window
    "NATURAL_LIGHT_HABITABLE", # Habitable room window area >= 10% floor area
    "TOILET_NO_VENTILATION",   # Toilet must have window or ventilation path
    "TOILET_VENTILATION",      # Alias / backward compat for toilet ventilation
    "PARKING_EXTERIOR_ACCESS", # Parking must have exterior road access
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

HABITABLE_ROOM_TYPES = frozenset({
    "living", "dining", "bedroom", "master_bedroom", "study", "foyer", "lobby",
})

ENTRANCE_FORBIDDEN_TYPES = frozenset({
    "bedroom", "master_bedroom", "toilet", "bathroom", "kitchen", "parking",
    "store", "utility", "dressing",
})


# ─────────────────────────────────────────────
# INDIVIDUAL AUDITABLE CONSTRAINT CHECKS
# ─────────────────────────────────────────────

def check_room_completeness(specs: List[RoomSpec], placed_room_ids: set) -> List[dict]:
    """Check that all requested rooms exist in the placed layout."""
    errors = []
    for spec in specs:
        if spec.id not in placed_room_ids:
            errors.append({
                "code": "ROOM_COMPLETENESS",
                "severity": "error",
                "message": f"Room '{spec.id}' ({spec.type}) was not placed.",
                "details": {"room_id": spec.id, "room_type": spec.type},
            })
    return errors


def check_room_area_minimum(
    room_polygons: Dict[str, Polygon],
    specs_by_id: Dict[str, RoomSpec],
    strict: bool = False,
) -> List[dict]:
    """Check that every room meets its minimum specified area."""
    errors = []
    for room_id, poly in room_polygons.items():
        spec = specs_by_id.get(room_id)
        if not spec:
            continue
        area_sqm = poly.area
        if area_sqm < spec.min_area_sqm:
            deficit_pct = (1.0 - area_sqm / spec.min_area_sqm) * 100
            if strict or deficit_pct > 30.0:
                errors.append({
                    "code": "ROOM_AREA_MINIMUM",
                    "severity": "error",
                    "message": (
                        f"Room '{room_id}' area {area_sqm * SQ_M_TO_SQ_FT:.1f} sqft "
                        f"is {deficit_pct:.1f}% below minimum {spec.min_area_sqm * SQ_M_TO_SQ_FT:.1f} sqft."
                    ),
                    "details": {
                        "room_id": room_id,
                        "room_type": spec.type,
                        "required": round(spec.min_area_sqm, 4),
                        "actual": round(area_sqm, 4),
                        "deficit_pct": round(deficit_pct, 2),
                    },
                })
    return errors


def check_room_no_overlap(
    room_polygons: Dict[str, Polygon],
    tolerance_sqm: float = 0.01,
) -> List[dict]:
    """Check that no two rooms overlap in interior area."""
    errors = []
    room_ids = list(room_polygons.keys())
    for i in range(len(room_ids)):
        for j in range(i + 1, len(room_ids)):
            id_a, id_b = room_ids[i], room_ids[j]
            pa, pb = room_polygons[id_a], room_polygons[id_b]
            if not pa.intersects(pb):
                continue
            inter = pa.intersection(pb)
            if not inter.is_empty and inter.area > tolerance_sqm:
                errors.append({
                    "code": "ROOM_NO_OVERLAP",
                    "severity": "error",
                    "message": f"Rooms '{id_a}' and '{id_b}' overlap by {inter.area:.3f} sqm.",
                    "details": {"room_a": id_a, "room_b": id_b, "overlap_area_sqm": round(inter.area, 4)},
                })
    return errors


def check_room_valid_geometry(room_polygons: Dict[str, Polygon]) -> List[dict]:
    """Check that all room polygons are valid and non-empty."""
    errors = []
    for room_id, poly in room_polygons.items():
        if not poly.is_valid or poly.is_empty or poly.area <= 0:
            errors.append({
                "code": "ROOM_VALID_GEOMETRY",
                "severity": "error",
                "message": f"Room '{room_id}' has invalid geometry.",
                "details": {"room_id": room_id},
            })
    return errors


def check_room_inside_boundary(
    room_polygons: Dict[str, Polygon],
    inner_polygon: Polygon,
    max_outside_pct: float = 5.0,
) -> List[dict]:
    """Check that rooms are fully contained within the buildable polygon."""
    errors = []
    for room_id, poly in room_polygons.items():
        if not inner_polygon.contains(poly):
            outside = poly.difference(inner_polygon)
            if not outside.is_empty and outside.area > poly.area * (max_outside_pct / 100.0):
                errors.append({
                    "code": "ROOM_INSIDE_BOUNDARY",
                    "severity": "error",
                    "message": f"Room '{room_id}' extends {outside.area:.3f} sqm outside buildable boundary.",
                    "details": {"room_id": room_id, "outside_area_sqm": round(outside.area, 4)},
                })
    return errors


def check_room_dimension_minimum(
    room_polygons: Dict[str, Polygon],
    specs_by_id: Dict[str, RoomSpec],
    strict: bool = False,
) -> List[dict]:
    """Check room minimum dimensions against specification."""
    from ..geometry.polygon_utils import min_dimension
    errors = []
    for room_id, poly in room_polygons.items():
        spec = specs_by_id.get(room_id)
        if not spec or spec.min_width_m <= 0:
            continue
        md = min_dimension(poly)
        if md < spec.min_width_m * (0.8 if not strict else 1.0):
            errors.append({
                "code": "ROOM_DIMENSION_MINIMUM",
                "severity": "error" if strict else "warning",
                "message": f"Room '{room_id}' min dimension {md:.2f}m is below minimum {spec.min_width_m:.2f}m.",
                "details": {"room_id": room_id, "actual_width": round(md, 3), "required_width": spec.min_width_m},
            })
    return errors


def check_room_aspect_ratio(
    room_polygons: Dict[str, Polygon],
    specs_by_id: Dict[str, RoomSpec],
    strict: bool = False,
) -> List[dict]:
    """Check room aspect ratios against specification."""
    from ..geometry.polygon_utils import aspect_ratio
    errors = []
    for room_id, poly in room_polygons.items():
        spec = specs_by_id.get(room_id)
        if not spec:
            continue
        ar = aspect_ratio(poly)
        if ar > spec.max_aspect_ratio * (1.5 if not strict else 1.0):
            errors.append({
                "code": "ROOM_ASPECT_RATIO",
                "severity": "error" if strict else "warning",
                "message": f"Room '{room_id}' aspect ratio {ar:.2f} exceeds maximum {spec.max_aspect_ratio:.2f}.",
                "details": {"room_id": room_id, "actual_ar": round(ar, 3), "max_ar": spec.max_aspect_ratio},
            })
    return errors


def check_circulation_connected(circulation_data: dict) -> List[dict]:
    """Check that all rooms are reachable from the entrance via the door graph."""
    if not circulation_data.get("connected", True):
        return [{
            "code": "CIRCULATION_CONNECTED",
            "severity": "error",
            "message": "One or more rooms are unreachable from the entrance via the door graph.",
            "details": {
                "reachable_rooms": circulation_data.get("reachable_rooms", 0),
                "total_rooms": circulation_data.get("total_rooms", 0),
            },
        }]
    return []


def check_entrance_room_type(entrance_room_type: str, room_id: str = "") -> List[dict]:
    """Check that main entrance is placed in an architecturally eligible room."""
    if entrance_room_type.lower() in ENTRANCE_FORBIDDEN_TYPES:
        return [{
            "code": "ENTRANCE_ROOM_TYPE",
            "severity": "error",
            "message": f"Entrance assigned to ineligible room type '{entrance_room_type}'.",
            "details": {"room_id": room_id, "room_type": entrance_room_type},
        }]
    return []


def check_no_forbidden_doors(doors: List[dict], room_types: Dict[str, str]) -> List[dict]:
    """Check that no forbidden-tier doors are present."""
    from ..config import DOOR_ADJACENCY_FORBIDDEN, ZONE_MAP
    from .doors import _matches
    errors = []
    for door in doors:
        t_a = room_types.get(door.get("from_room", ""), "").lower()
        t_b = room_types.get(door.get("to_room", ""), "").lower()
        is_forbidden = _matches(DOOR_ADJACENCY_FORBIDDEN, t_a, t_b)
        if not is_forbidden:
            z_a = ZONE_MAP.get(t_a, "")
            z_b = ZONE_MAP.get(t_b, "")
            if z_a == "private" and z_b == "private" and t_a != "corridor" and t_b != "corridor":
                is_forbidden = True
        if is_forbidden:
            errors.append({
                "code": "NO_FORBIDDEN_DOORS",
                "severity": "error",
                "message": f"Forbidden door {door.get('id')} connects '{door.get('from_room')}' ({t_a}) ↔ '{door.get('to_room')}' ({t_b}).",
                "details": {"door_id": door.get("id"), "from_type": t_a, "to_type": t_b},
            })
    return errors


def check_habitable_room_window(
    room_types: Dict[str, str],
    rooms_with_windows: set,
) -> List[dict]:
    """Habitable rooms must have at least one window."""
    errors = []
    for room_id, rtype in room_types.items():
        if rtype.lower() in HABITABLE_ROOM_TYPES and room_id not in rooms_with_windows:
            errors.append({
                "code": "HABITABLE_ROOM_WINDOW",
                "severity": "error",
                "message": f"Habitable room '{room_id}' (type: {rtype}) has no window.",
                "details": {"room_id": room_id, "room_type": rtype},
            })
    return errors


def check_natural_light_habitable(
    room_polygons: Dict[str, Polygon],
    room_types: Dict[str, str],
    windows: List[dict],
) -> List[dict]:
    """Habitable rooms must have total window area >= 10% of floor area."""
    errors = []
    windows_by_room: Dict[str, List[dict]] = {}
    for w in windows:
        windows_by_room.setdefault(w.get("room_id", ""), []).append(w)

    for room_id, rtype in room_types.items():
        if rtype.lower() in HABITABLE_ROOM_TYPES:
            poly = room_polygons.get(room_id)
            if not poly or poly.is_empty:
                continue
            fl_area = poly.area
            req_win_area = fl_area * 0.10
            r_wins = windows_by_room.get(room_id, [])
            act_win_area = sum(
                w.get("width", 0.0) * (w.get("height_m") or (0.6 if w.get("type") == "ventilation" else 1.2))
                for w in r_wins
            )
            if act_win_area < req_win_area - 0.01:
                errors.append({
                    "code": "NATURAL_LIGHT_HABITABLE",
                    "severity": "error",
                    "message": (
                        f"Habitable room '{room_id}' (type: {rtype}) has window area {act_win_area:.2f} sqm, "
                        f"which is below the required 10% of floor area ({req_win_area:.2f} sqm for {fl_area:.2f} sqm floor)."
                    ),
                    "details": {
                        "room_id": room_id,
                        "room_type": rtype,
                        "floor_area_sqm": round(fl_area, 4),
                        "window_area_sqm": round(act_win_area, 4),
                        "required_window_area_sqm": round(req_win_area, 4),
                        "ratio": round(act_win_area / fl_area if fl_area > 0 else 0, 4),
                    },
                })
    return errors


def check_toilet_ventilation(
    room_polygons: Dict[str, Polygon],
    room_types: Dict[str, str],
    rooms_with_windows: set,
    corridor_polys: Optional[List[Polygon]] = None,
    other_polygons: Optional[Dict[str, Polygon]] = None,
) -> List[dict]:
    """
    Toilets must have an exterior window or a mechanical ventilation path
    (via corridor, parking, utility, or ventilation shaft).
    """
    errors = []
    VENT_PATH_TYPES = {"corridor", "parking", "utility", "shaft"}

    for room_id, rtype in room_types.items():
        if rtype.lower() in ("toilet", "bathroom"):
            has_win = room_id in rooms_with_windows
            has_vent_path = False
            poly = room_polygons.get(room_id)
            if poly:
                if corridor_polys:
                    for cpoly in corridor_polys:
                        if poly.intersects(cpoly) and poly.intersection(cpoly).length >= 0.1:
                            has_vent_path = True
                            break
                if not has_vent_path and other_polygons:
                    for other_id, other_poly in other_polygons.items():
                        other_t = room_types.get(other_id, "").lower()
                        if other_t in VENT_PATH_TYPES and other_id != room_id:
                            if poly.intersects(other_poly) and poly.intersection(other_poly).length >= 0.1:
                                has_vent_path = True
                                break

            if not has_win and not has_vent_path:
                errors.append({
                    "code": "TOILET_NO_VENTILATION",
                    "severity": "error",
                    "message": (
                        f"Toilet/bathroom '{room_id}' has neither a window nor a ventilation path. "
                        "Interior toilets require an exterior window or mechanical ventilation via corridor/shaft."
                    ),
                    "details": {"room_id": room_id, "room_type": rtype},
                })
    return errors


def check_parking_exterior_access(parking_entities: List[dict]) -> List[dict]:
    """Check that parking has road-side exterior wall access."""
    errors = []
    for p in parking_entities:
        if not p.get("road_access", True):
            errors.append({
                "code": "PARKING_EXTERIOR_ACCESS",
                "severity": "error",
                "message": f"Parking '{p.get('id')}' has no exterior road access.",
                "details": {"parking_id": p.get("id")},
            })
    return errors


def check_parking_dimensions(parking_entities: List[dict], strict: bool = False) -> List[dict]:
    """Check that parking meets minimum width and length."""
    errors = []
    for p in parking_entities:
        if not p.get("meets_minimum", True):
            errors.append({
                "code": "PARKING_DIMENSIONS",
                "severity": "error" if strict else "warning",
                "message": f"Parking '{p.get('id')}' does not meet minimum dimensions (2.5m x 5.0m).",
                "details": p,
            })
    return errors
