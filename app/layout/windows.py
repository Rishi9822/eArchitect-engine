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

    import math
    from ..geometry.polygon_utils import line_orientation

    for room_id, room_poly in room_polygons.items():
        room_type = room_types.get(room_id, "")
        defaults = get_room_defaults(room_type)

        # Find exterior edges for this room
        ext_edges = _find_exterior_edges(room_poly, inner_polygon)
        if not ext_edges:
            continue

        # Determine window parameters based on room type
        is_habitable = room_type in ("bedroom", "living", "dining", "master_bedroom", "study", "foyer", "lobby")
        if room_type in ("toilet", "bathroom"):
            window_width = VENTILATION_WINDOW_WIDTH_M
            window_height = 0.6
            window_type = "ventilation"
            sill_height = defaults.window_sill_height_m
            max_windows = 1
            needed_area = 0.0
        elif is_habitable:
            needed_area = room_poly.area * 0.10
            window_height = 1.2
            base_width = defaults.default_window_width_m
            needed_width = needed_area / window_height
            window_type = "standard"
            sill_height = DEFAULT_SILL_HEIGHT_M
            max_windows = max(2 if natural_light_priority else 1, math.ceil(needed_width / base_width))
            window_width = base_width
        elif room_type == "kitchen":
            window_width = defaults.default_window_width_m
            window_height = 1.2
            window_type = "standard"
            sill_height = DEFAULT_SILL_HEIGHT_M
            max_windows = 1
            needed_area = 0.0
        elif room_type in ("store", "utility", "parking"):
            continue  # No windows for these types
        else:
            window_width = DEFAULT_WINDOW_WIDTH_M
            window_height = 1.2
            window_type = "standard"
            sill_height = DEFAULT_SILL_HEIGHT_M
            max_windows = 1
            needed_area = 0.0

        # Sort exterior edges by length (prefer longer walls)
        ext_edges.sort(key=lambda e: e.length, reverse=True)

        placed = 0
        placed_area = 0.0
        for edge in ext_edges:
            if placed >= max_windows and (not is_habitable or placed_area >= needed_area - 0.01):
                break

            curr_width = window_width
            can_fit_two = False
            if is_habitable and placed_area < needed_area - 0.01:
                rem_width = (needed_area - placed_area) / window_height
                if rem_width > 2.4 or (edge.length >= 2 * window_width + 0.8 and rem_width > window_width):
                    target_w = min(2.4, max(MIN_WINDOW_WIDTH_M, rem_width / 2))
                    if edge.length >= 2 * target_w + 0.6 and (placed + 2 <= max_windows):
                        curr_width = target_w
                        can_fit_two = True
                    elif edge.length >= rem_width + 0.4:
                        curr_width = min(2.4, round(rem_width, 2))
                elif rem_width > curr_width and edge.length >= rem_width + 0.4:
                    curr_width = min(2.4, round(rem_width, 2))

            if not can_fit_two:
                if edge.length < curr_width + 0.3:
                    if edge.length >= window_width + 0.3:
                        curr_width = window_width
                    elif edge.length >= MIN_WINDOW_WIDTH_M + 0.3:
                        curr_width = MIN_WINDOW_WIDTH_M
                    else:
                        continue

            if can_fit_two:
                for frac in (0.33, 0.67):
                    mid = edge.interpolate(frac, normalized=True)
                    orientation = line_orientation(edge)
                    windows.append({
                        "id": f"WIN{window_counter:03d}",
                        "room_id": room_id,
                        "wall_id": None,
                        "position": {"x": round(mid.x, 4), "y": round(mid.y, 4)},
                        "width": round(curr_width, 3),
                        "height_m": round(window_height, 2),
                        "area_sqm": round(curr_width * window_height, 4),
                        "type": window_type,
                        "sill_height_m": sill_height,
                        "orientation": orientation,
                    })
                    window_counter += 1
                    placed += 1
                    placed_area += curr_width * window_height
            else:
                mid = edge.interpolate(0.5, normalized=True)
                orientation = line_orientation(edge)
                windows.append({
                    "id": f"WIN{window_counter:03d}",
                    "room_id": room_id,
                    "wall_id": None,
                    "position": {"x": round(mid.x, 4), "y": round(mid.y, 4)},
                    "width": round(curr_width, 3),
                    "height_m": round(window_height, 2),
                    "area_sqm": round(curr_width * window_height, 4),
                    "type": window_type,
                    "sill_height_m": sill_height,
                    "orientation": orientation,
                })
                window_counter += 1
                placed += 1
                placed_area += curr_width * window_height

    logger.info("Generated %d windows", len(windows))
    return windows
