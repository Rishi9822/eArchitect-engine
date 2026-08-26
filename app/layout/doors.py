"""
Internal door generation.

Places doors on shared walls between adjacent rooms.
Uses room-type-aware default widths.
"""
from __future__ import annotations

import logging
from typing import List, Dict, Optional

from shapely.geometry import Polygon, LineString

from ..config import (
    DEFAULT_DOOR_WIDTH_M,
    MIN_WALL_FOR_DOOR_M,
    get_room_defaults,
)
from ..geometry.polygon_utils import polygons_share_boundary

logger = logging.getLogger(__name__)


def _find_shared_wall(poly_a: Polygon, poly_b: Polygon) -> Optional[LineString]:
    """
    Find the shared boundary segment between two room polygons.
    Returns the longest shared segment as a LineString.
    """
    try:
        inters = poly_a.boundary.intersection(poly_b.boundary)
        if inters.is_empty:
            return None

        # Extract longest linear piece
        if hasattr(inters, "geoms"):
            lines = [g for g in inters.geoms
                     if isinstance(g, LineString) and g.length >= MIN_WALL_FOR_DOOR_M]
            if not lines:
                return None
            return max(lines, key=lambda l: l.length)
        elif isinstance(inters, LineString) and inters.length >= MIN_WALL_FOR_DOOR_M:
            return inters

        return None
    except Exception:
        return None


def generate_doors(
    room_polygons: Dict[str, Polygon],
    room_types: Dict[str, str],
    entrance_room_id: Optional[str] = None,
) -> List[dict]:
    """
    Generate internal doors between adjacent rooms.

    Rules:
    1. Place a door on every shared wall between adjacent rooms
       (if wall is long enough)
    2. Use room-type-aware default widths
    3. Skip duplicate pairs

    Args:
        room_polygons: {room_id: Polygon}
        room_types:    {room_id: room_type_str}
        entrance_room_id: room connected to main entrance

    Returns:
        list of door dicts
    """
    doors: List[dict] = []
    door_counter = 1
    processed_pairs = set()

    room_ids = list(room_polygons.keys())

    for i in range(len(room_ids)):
        for j in range(i + 1, len(room_ids)):
            id_a, id_b = room_ids[i], room_ids[j]
            pair_key = tuple(sorted([id_a, id_b]))

            if pair_key in processed_pairs:
                continue

            poly_a = room_polygons[id_a]
            poly_b = room_polygons[id_b]

            if not polygons_share_boundary(poly_a, poly_b, min_length=MIN_WALL_FOR_DOOR_M):
                continue

            shared = _find_shared_wall(poly_a, poly_b)
            if shared is None:
                continue

            processed_pairs.add(pair_key)

            # Determine door width from room types
            type_a = room_types.get(id_a, "")
            type_b = room_types.get(id_b, "")
            defaults_a = get_room_defaults(type_a)
            defaults_b = get_room_defaults(type_b)
            door_width = min(defaults_a.default_door_width_m,
                             defaults_b.default_door_width_m)

            # Check wall is long enough
            if shared.length < door_width + 0.2:
                continue

            # Place door at midpoint of shared wall
            mid = shared.interpolate(0.5, normalized=True)

            # Determine door type
            door_type = "internal"
            if type_a == "parking" or type_b == "parking":
                door_type = "service"

            doors.append({
                "id": f"D{door_counter:03d}",
                "type": door_type,
                "width": round(door_width, 3),
                "position": {"x": round(mid.x, 4), "y": round(mid.y, 4)},
                "wall_id": None,  # Resolved after wall extraction
                "from_room": id_a,
                "to_room": id_b,
            })
            door_counter += 1

    logger.info("Generated %d internal doors", len(doors))
    return doors
