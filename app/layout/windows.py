"""
Window placement on exterior walls.

Places windows primarily on exterior walls, with priority
for rooms requiring natural light and ventilation.
"""
from __future__ import annotations

import logging
from typing import List, Dict, Optional

from shapely.geometry import Polygon, LineString

from ..config import (
    DEFAULT_WINDOW_WIDTH_M,
    MIN_WINDOW_WIDTH_M,
    VENTILATION_WINDOW_WIDTH_M,
    DEFAULT_SILL_HEIGHT_M,
    MIN_WALL_FOR_WINDOW_M,
    get_room_defaults,
)
from ..geometry.polygon_utils import polygon_edges, polygon_exterior_contact

logger = logging.getLogger(__name__)


def _find_exterior_edges(
    room_poly: Polygon,
    boundary_poly: Polygon,
    min_length: float = MIN_WALL_FOR_WINDOW_M,
) -> List[LineString]:
    """
    Find edges of a room polygon that lie on the exterior boundary.
    """
    boundary = boundary_poly.boundary
    boundary_buf = boundary.buffer(0.08)  # tolerance for BSP-generated edges
    result = []

    for edge in polygon_edges(room_poly):
        if edge.length < min_length:
            continue
        overlap = edge.intersection(boundary_buf)
        if not overlap.is_empty and overlap.length >= min_length * 0.5:
            result.append(edge)

    return result


def generate_windows(
    room_polygons: Dict[str, Polygon],
    room_types: Dict[str, str],
    inner_polygon: Polygon,
    preferences: dict,
) -> List[dict]:
    """
    Generate windows for rooms, primarily on exterior walls.

    Priority:
    1. Rooms requiring natural light (bedroom, living, dining)
    2. Rooms requiring ventilation (kitchen, toilet, bathroom)
    3. Standard windows for other rooms with exterior walls

    Args:
        room_polygons: {room_id: Polygon}
        room_types:    {room_id: room_type_str}
        inner_polygon: buildable boundary
        preferences:   user preferences dict

    Returns:
        list of window dicts
    """
    windows: List[dict] = []
    window_counter = 1

    natural_light_priority = preferences.get("natural_light_priority", False)
    ventilation_priority = preferences.get("ventilation_priority", False)

    for room_id, room_poly in room_polygons.items():
        room_type = room_types.get(room_id, "")
        defaults = get_room_defaults(room_type)

        # Find exterior edges for this room
        ext_edges = _find_exterior_edges(room_poly, inner_polygon)
        if not ext_edges:
            continue

        # Determine window parameters based on room type
        if room_type in ("toilet", "bathroom"):
            window_width = VENTILATION_WINDOW_WIDTH_M
            window_type = "ventilation"
            sill_height = defaults.window_sill_height_m
            max_windows = 1
        elif room_type in ("bedroom", "living", "dining", "master_bedroom"):
            window_width = defaults.default_window_width_m
            window_type = "standard"
            sill_height = DEFAULT_SILL_HEIGHT_M
            # Add extra windows if natural light priority
            max_windows = 2 if natural_light_priority else 1
        elif room_type == "kitchen":
            window_width = defaults.default_window_width_m
            window_type = "standard"
            sill_height = DEFAULT_SILL_HEIGHT_M
            max_windows = 1
        elif room_type in ("store", "utility", "parking"):
            continue  # No windows for these types
        else:
            window_width = DEFAULT_WINDOW_WIDTH_M
            window_type = "standard"
            sill_height = DEFAULT_SILL_HEIGHT_M
            max_windows = 1

        # Sort exterior edges by length (prefer longer walls)
        ext_edges.sort(key=lambda e: e.length, reverse=True)

        placed = 0
        for edge in ext_edges:
            if placed >= max_windows:
                break
            if edge.length < window_width + 0.3:
                continue

            mid = edge.interpolate(0.5, normalized=True)
            from ..geometry.polygon_utils import line_orientation
            orientation = line_orientation(edge)

            windows.append({
                "id": f"WIN{window_counter:03d}",
                "room_id": room_id,
                "wall_id": None,  # Resolved after wall extraction
                "position": {"x": round(mid.x, 4), "y": round(mid.y, 4)},
                "width": round(window_width, 3),
                "type": window_type,
                "sill_height_m": sill_height,
                "orientation": orientation,
            })
            window_counter += 1
            placed += 1

    logger.info("Generated %d windows", len(windows))
    return windows
