"""
Parking constraint validation and entity generation.

Parking is treated as a specialized architectural entity
with minimum dimensional requirements and road accessibility.
"""
from __future__ import annotations

import logging
from typing import List, Dict, Optional

from shapely.geometry import Polygon

from ..config import (
    PARKING_MIN_WIDTH_M,
    PARKING_MIN_LENGTH_M,
    PARKING_CLEARANCE_M,
    SQ_M_TO_SQ_FT,
    ZONE_MAP,
)
from ..geometry.polygon_utils import min_dimension, max_dimension, polygon_exterior_contact

logger = logging.getLogger(__name__)


def validate_parking(
    parking_poly: Polygon,
    inner_polygon: Polygon,
    facing: str,
    road_side: str,
) -> dict:
    """
    Validate parking dimensions and road accessibility.

    Args:
        parking_poly:  parking room polygon
        inner_polygon: buildable boundary
        facing:        plot facing direction
        road_side:     road side of the plot

    Returns:
        dict with validation results
    """
    width = min_dimension(parking_poly)
    length = max_dimension(parking_poly)

    meets_width = width >= PARKING_MIN_WIDTH_M * 0.85  # small tolerance
    meets_length = length >= PARKING_MIN_LENGTH_M * 0.85

    # Check road access: parking should touch exterior boundary
    ext_contact = polygon_exterior_contact(parking_poly, inner_polygon, min_length=1.0)
    has_road_access = ext_contact >= 1.0

    return {
        "width_m": round(width, 3),
        "length_m": round(length, 3),
        "meets_width": meets_width,
        "meets_length": meets_length,
        "meets_minimum": meets_width and meets_length,
        "road_access": has_road_access,
        "exterior_contact_m": round(ext_contact, 3),
    }


def generate_parking_entities(
    room_polygons: Dict[str, Polygon],
    room_types: Dict[str, str],
    inner_polygon: Polygon,
    facing: str,
    road_side: str,
) -> List[dict]:
    """
    Generate parking entities from parking room polygons.

    Args:
        room_polygons: {room_id: Polygon}
        room_types:    {room_id: room_type_str}
        inner_polygon: buildable boundary
        facing:        plot facing direction
        road_side:     road side

    Returns:
        list of parking entity dicts
    """
    parking_entities = []
    counter = 1

    for room_id, poly in room_polygons.items():
        rtype = room_types.get(room_id, "")
        if rtype != "parking":
            continue

        validation = validate_parking(poly, inner_polygon, facing, road_side)

        coords = [
            {"x": round(x, 4), "y": round(y, 4)}
            for x, y in list(poly.exterior.coords)[:-1]
        ]

        parking_entities.append({
            "id": f"P{counter:03d}",
            "room_id": room_id,
            "polygon": coords,
            "vehicle_type": "car",
            "width_m": validation["width_m"],
            "length_m": validation["length_m"],
            "area_sqft": round(poly.area * SQ_M_TO_SQ_FT, 2),
            "area_sqm": round(poly.area, 4),
            "road_access": validation["road_access"],
            "meets_minimum": validation["meets_minimum"],
        })
        counter += 1

    return parking_entities
