"""
Entrance placement on the buildable boundary.

Places the main entrance on the requested side (front/back/left/right)
of the buildable polygon, finding the best exterior wall to host it.
"""
from __future__ import annotations

import math
import logging
from typing import List, Dict, Optional, Tuple

from shapely.geometry import Polygon, LineString, Point as ShapelyPoint

from ..config import MAIN_ENTRANCE_WIDTH_M, ZONE_MAP
from ..geometry.polygon_utils import polygon_edges, line_bearing

logger = logging.getLogger(__name__)


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


def find_entrance_wall(
    inner_polygon: Polygon,
    room_polygons: Dict[str, Polygon],
    room_types: Dict[str, str],
    side: str,
    facing: str,
    entrance_width: float = MAIN_ENTRANCE_WIDTH_M,
) -> Optional[dict]:
    """
    Find the best exterior wall segment for entrance placement.

    Priority:
    1. Exterior wall on the requested side
    2. Adjacent to a public room (living, dining, foyer)
    3. Long enough to host the entrance

    Returns:
        dict with entrance data or None if no suitable wall found
    """
    lo, hi = _side_to_bearing_range(side, facing)
    boundary_edges = polygon_edges(inner_polygon)

    candidates = []

    for edge in boundary_edges:
        if edge.length < entrance_width:
            continue

        bearing = line_bearing(edge)
        # We want edges perpendicular to the side direction
        # An edge on the "front" side has a bearing ~perpendicular to front facing
        edge_normal = (bearing + 90) % 360

        if _bearing_in_range(edge_normal, lo, hi) or _bearing_in_range(bearing, lo, hi):
            # Find which room this edge is closest to
            midpoint = edge.interpolate(0.5, normalized=True)
            best_room = None
            best_dist = float("inf")
            is_public = False

            for room_id, room_poly in room_polygons.items():
                if room_poly.is_empty or not room_poly.is_valid:
                    continue
                try:
                    dist = room_poly.distance(midpoint)
                    if dist < best_dist:
                        best_dist = dist
                        best_room = room_id
                        rtype = room_types.get(room_id, "")
                        is_public = ZONE_MAP.get(rtype, "") == "public"
                except Exception:
                    continue

            candidates.append({
                "edge": edge,
                "bearing": bearing,
                "room_id": best_room,
                "is_public": is_public,
                "length": edge.length,
            })

    if not candidates:
        # Fallback: try any boundary edge long enough
        for edge in boundary_edges:
            if edge.length >= entrance_width:
                midpoint = edge.interpolate(0.5, normalized=True)
                best_room = None
                best_dist = float("inf")
                for room_id, room_poly in room_polygons.items():
                    if room_poly.is_empty or not room_poly.is_valid:
                        continue
                    try:
                        dist = room_poly.distance(midpoint)
                        if dist < best_dist:
                            best_dist = dist
                            best_room = room_id
                    except Exception:
                        continue

                candidates.append({
                    "edge": edge,
                    "bearing": line_bearing(edge),
                    "room_id": best_room,
                    "is_public": False,
                    "length": edge.length,
                })

    if not candidates:
        return None

    # Sort: prefer public-adjacent, then longest
    candidates.sort(key=lambda c: (-c["is_public"], -c["length"]))
    best = candidates[0]

    # Place entrance at midpoint of edge
    edge = best["edge"]
    mid = edge.interpolate(0.5, normalized=True)

    return {
        "position": {"x": round(mid.x, 4), "y": round(mid.y, 4)},
        "width": entrance_width,
        "side": side,
        "room_id": best["room_id"],
        "direction": f"{best['bearing']:.0f}deg",
        "edge": edge,
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
        Entrance dict or None
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
