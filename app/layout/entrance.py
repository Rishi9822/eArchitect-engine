"""
Entrance placement on the buildable boundary.

Priority 2 (Architectural Logic):
  - Select entrance room BEFORE door graph is built.
  - Eligible room types (in preference order): foyer > living > corridor > dining
  - NEVER eligible: bedroom, toilet, kitchen, parking, bathroom, store, utility,
    dressing, master_bedroom, study
  - Selection is based on which eligible room has the longest shared boundary
    segment on the road-facing side of the buildable polygon.
  - If no eligible room touches the road-facing side, emit ENTRANCE_NO_ELIGIBLE_ROOM.
"""
from __future__ import annotations

import math
import logging
from typing import List, Dict, Optional, Tuple

from shapely.geometry import Polygon, LineString, Point as ShapelyPoint
from shapely.ops import linemerge

from ..config import MAIN_ENTRANCE_WIDTH_M, ZONE_MAP
from ..geometry.polygon_utils import polygon_edges, line_bearing

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# PRIORITY 2: Entrance-eligible room types
# Lower rank number = higher preference
# ─────────────────────────────────────────────

ENTRANCE_ROOM_PRIORITY: Dict[str, int] = {
    "foyer":    1,
    "living":   2,
    "corridor": 3,
    "dining":   4,
}

# Room types that are NEVER allowed to host the main entrance.
ENTRANCE_INELIGIBLE_TYPES = frozenset({
    "bedroom",
    "master_bedroom",
    "toilet",
    "bathroom",
    "kitchen",
    "parking",
    "store",
    "utility",
    "dressing",
    "study",
})


def _side_to_bearing_range(
    side: str, facing: str
) -> Tuple[float, float]:
    """
    Map a logical side (front/back/left/right) to a bearing range
    based on plot facing direction.

    The 'front' side faces the road (facing direction).
    """
    # facing → bearing of the front side (direction the front faces)
    facing_bearings = {
        "north": 0,
        "east": 90,
        "south": 180,
        "west": 270,
    }
    base = facing_bearings.get(facing, 0)

    side_offsets = {
        "front": 0,
        "right": 90,
        "back": 180,
        "left": 270,
    }
    offset = side_offsets.get(side, 0)

    center = (base + offset) % 360
    # Accept edges within ±60° of the target bearing
    lo = (center - 60) % 360
    hi = (center + 60) % 360
    return lo, hi


def _bearing_in_range(bearing: float, lo: float, hi: float) -> bool:
    """Check if a bearing falls within [lo, hi], handling wrap-around."""
    bearing = bearing % 360
    if lo <= hi:
        return lo <= bearing <= hi
    else:
        # Wraps around 360
        return bearing >= lo or bearing <= hi



def _road_side_boundary(
    inner_polygon: Polygon,
    side: str,
    facing: str,
) -> Optional[LineString]:
    """
    Return a merged LineString representing all boundary edges of
    inner_polygon that face the requested road side.

    Returns None if no suitable edges exist.
    """
    lo, hi = _side_to_bearing_range(side, facing)
    road_edges = []

    for edge in polygon_edges(inner_polygon):
        bearing = line_bearing(edge)
        edge_normal = (bearing + 90) % 360
        if _bearing_in_range(edge_normal, lo, hi) or _bearing_in_range(bearing, lo, hi):
            road_edges.append(edge)

    if not road_edges:
        return None

    merged = linemerge(road_edges)
    return merged


def _shared_road_length(
    room_poly: Polygon,
    road_boundary: LineString,
    buffer_m: float = 0.05,
) -> float:
    """
    Return the total length of room_poly's boundary that lies on the
    road-facing boundary (within buffer_m tolerance).
    """
    try:
        contact = room_poly.boundary.intersection(road_boundary.buffer(buffer_m))
        if contact.is_empty:
            return 0.0
        return contact.length
    except Exception:
        return 0.0


def _midpoint_on_shared_boundary(
    room_poly: Polygon,
    road_boundary: LineString,
    buffer_m: float = 0.05,
) -> Optional[dict]:
    """
    Return the midpoint of the shared boundary segment between room_poly
    and road_boundary, as {"x": ..., "y": ...}.
    """
    try:
        contact = room_poly.boundary.intersection(road_boundary.buffer(buffer_m))
        if contact.is_empty:
            return None
        # Get longest component when result is a collection
        if hasattr(contact, "geoms"):
            contact = max(contact.geoms, key=lambda g: g.length)
        if contact.length < 1e-4:
            return None
        mid = contact.interpolate(0.5, normalized=True)
        return {"x": round(mid.x, 4), "y": round(mid.y, 4)}
    except Exception:
        return None


def find_entrance_wall(
    inner_polygon: Polygon,
    room_polygons: Dict[str, Polygon],
    room_types: Dict[str, str],
    side: str,
    facing: str,
    entrance_width: float = MAIN_ENTRANCE_WIDTH_M,
) -> Optional[dict]:
    """
    Find the best room and wall segment for entrance placement.

    Priority 2 logic:
      1. Build road-facing boundary from inner_polygon edges.
      2. For each room, measure shared boundary with road side.
      3. Only eligible room types may host the entrance:
             foyer > living > corridor > dining
      4. Among eligible rooms, rank by ENTRANCE_ROOM_PRIORITY then by
         shared boundary length (longer is better).
      5. Return entrance dict with room_id, position, bearing, and edge.
         Returns None if no eligible room found (caller must emit
         ENTRANCE_NO_ELIGIBLE_ROOM validation error).
    """
    road_boundary = _road_side_boundary(inner_polygon, side, facing)

    if road_boundary is None:
        logger.warning(
            "No road-facing boundary edges found for side='%s' facing='%s'", side, facing
        )
        return None

    # ── Collect candidates by eligible room type ───────────────────
    eligible: List[dict] = []
    ineligible_on_road: List[str] = []  # rooms that touch road but are wrong type

    for room_id, room_poly in room_polygons.items():
        if room_poly.is_empty or not room_poly.is_valid:
            continue

        rtype = room_types.get(room_id, "")
        shared_len = _shared_road_length(room_poly, road_boundary)

        if shared_len < entrance_width:
            # Room wall too short for entrance, or doesn't touch road side
            continue

        if rtype in ENTRANCE_INELIGIBLE_TYPES:
            ineligible_on_road.append(room_id)
            logger.debug(
                "Room %s (type=%s) touches road side (%.2fm) but is ineligible for entrance",
                room_id, rtype, shared_len,
            )
            continue

        priority = ENTRANCE_ROOM_PRIORITY.get(rtype)
        if priority is None:
            # Unknown / unlisted room type — treat as lowest-priority eligible
            priority = 99

        eligible.append({
            "room_id": room_id,
            "room_type": rtype,
            "priority": priority,
            "shared_length": shared_len,
        })

    if not eligible:
        if ineligible_on_road:
            logger.warning(
                "Entrance side '%s': only ineligible rooms touch road boundary: %s",
                side, ineligible_on_road,
            )
        else:
            logger.warning(
                "Entrance side '%s': no rooms touch road boundary with sufficient width",
                side,
            )
        return None

    # ── Sort: lower priority number first, then longer shared boundary ─
    eligible.sort(key=lambda c: (c["priority"], -c["shared_length"]))
    best = eligible[0]
    best_room_poly = room_polygons[best["room_id"]]

    # ── Compute midpoint position on shared road boundary ─────────
    position = _midpoint_on_shared_boundary(best_room_poly, road_boundary)
    if position is None:
        logger.error(
            "Could not compute midpoint for entrance room %s", best["room_id"]
        )
        return None

    # ── Compute door bearing (inward-facing from road boundary) ───
    try:
        if hasattr(road_boundary, "geoms"):
            # MultiLineString — use the segment closest to our position
            pos_pt = ShapelyPoint(position["x"], position["y"])
            road_seg = min(road_boundary.geoms, key=lambda g: g.distance(pos_pt))
        else:
            road_seg = road_boundary
        bearing = line_bearing(road_seg)
    except Exception:
        bearing = 0.0

    logger.info(
        "Entrance placed on room %s (type=%s, priority=%d, shared=%.2fm)",
        best["room_id"], best["room_type"], best["priority"], best["shared_length"],
    )

    return {
        "position": position,
        "width": entrance_width,
        "side": side,
        "room_id": best["room_id"],
        "direction": f"{bearing:.0f}deg",
        "edge": road_boundary,
        # Diagnostic fields (not in output schema)
        "_entrance_room_type": best["room_type"],
        "_entrance_priority": best["priority"],
    }


def generate_entrance(
    inner_polygon: Polygon,
    room_polygons: Dict[str, Polygon],
    room_types: Dict[str, str],
    entrance_config: dict,
    facing: str,
) -> Optional[dict]:
    """
    Generate the main entrance entity.

    Args:
        inner_polygon:   buildable boundary polygon
        room_polygons:   {room_id: Polygon}
        room_types:      {room_id: room_type_str}
        entrance_config: {'side': str, 'width': float}
        facing:          plot facing direction

    Returns:
        Entrance dict or None.  When None, the caller should emit
        ENTRANCE_NO_ELIGIBLE_ROOM as a hard validation error.
    """
    side = entrance_config.get("side", "front")
    width = entrance_config.get("width", MAIN_ENTRANCE_WIDTH_M)

    result = find_entrance_wall(
        inner_polygon, room_polygons, room_types,
        side, facing, width,
    )

    if result is None:
        logger.warning("Could not place entrance on side '%s'", side)
        return None

    return {
        "id": "ENT001",
        "type": "main",
        "side": side,
        "position": result["position"],
        "width": width,
        "wall_id": None,  # Will be resolved after wall extraction
        "room_id": result["room_id"],
        "direction": result["direction"],
    }
