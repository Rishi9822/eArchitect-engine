"""
Parking constraint validation and entity generation.

Priority 8 Implementation:
- Fixed-footprint parking placement (2.5m x 5.0m clear per car + 0.5m margin = 3.0m x 5.5m)
  placed directly along the road-side boundary BEFORE BSP partitioning.
- Leftover area returned to BSP pool for habitable rooms (parking drops from ~45 sqm to 16.5 sqm).
- Exterior shutter door generation (>= 2.4m) on the parking room's road-facing exterior wall.
- Auditable PARKING_EXTERIOR_ACCESS constraint check.
"""
from __future__ import annotations

import math
import random
import logging
from typing import List, Dict, Optional, Tuple

from shapely.geometry import Polygon, LineString, Point, MultiLineString

from ..config import (
    PARKING_MIN_WIDTH_M,
    PARKING_MIN_LENGTH_M,
    PARKING_CLEARANCE_M,
    PARKING_FIXED_WIDTH_M,
    PARKING_FIXED_LENGTH_M,
    PARKING_FIXED_AREA_SQM,
    PARKING_SHUTTER_WIDTH_M,
    SQ_M_TO_SQ_FT,
    ZONE_MAP,
)
from ..geometry.normalization import ensure_valid
from ..geometry.polygon_utils import min_dimension, max_dimension, polygon_exterior_contact
from .entrance import _road_side_boundary

logger = logging.getLogger(__name__)


def place_fixed_parking(
    inner_polygon: Polygon,
    road_side: str,
    facing: str,
    rng: Optional[random.Random] = None,
    car_count: int = 1,
    width_m: float = PARKING_FIXED_WIDTH_M,
    length_m: float = PARKING_FIXED_LENGTH_M,
) -> Tuple[Optional[Polygon], Polygon]:
    """
    Carve a fixed-footprint parking space (2.5m x 5.0m clear per car + 0.5m margin)
    directly along the road-side boundary of inner_polygon *before* BSP partitioning.

    Returns:
        (parking_polygon, remaining_house_polygon)
        If parking cannot be placed, returns (None, inner_polygon).
    """
    road_boundary = _road_side_boundary(inner_polygon, road_side, facing)
    if road_boundary is None or road_boundary.is_empty:
        return None, inner_polygon

    # Decompose into 2-point segments
    def _extract_segments(geom) -> List[LineString]:
        segs = []
        if hasattr(geom, "geoms"):
            for g in geom.geoms:
                segs.extend(_extract_segments(g))
        elif isinstance(geom, LineString):
            coords = list(geom.coords)
            for i in range(len(coords) - 1):
                s = LineString([coords[i], coords[i + 1]])
                if s.length >= 0.5:
                    segs.append(s)
        return segs

    road_segs = _extract_segments(road_boundary)
    if not road_segs:
        return None, inner_polygon

    # Sort segments by length descending
    road_segs.sort(key=lambda s: -s.length)

    req_width = width_m * car_count
    req_depth = length_m

    prefer_corner = 1 if (rng is not None and rng.random() >= 0.5) else 0

    for seg in road_segs:
        if seg.length < req_width * 0.95:
            continue

        c = list(seg.coords)
        p0, p1 = c[0], c[-1]
        dx = p1[0] - p0[0]
        dy = p1[1] - p0[1]
        L = math.hypot(dx, dy)
        if L < 1e-4:
            continue
        u = (dx / L, dy / L)
        na = (-u[1], u[0])
        nb = (u[1], -u[0])
        mid = Point((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
        test_a = Point(mid.x + 0.1 * na[0], mid.y + 0.1 * na[1])
        n_in = na if inner_polygon.contains(test_a) else nb

        # Corner 0 candidate
        c0_1 = p0
        c0_2 = (p0[0] + req_width * u[0], p0[1] + req_width * u[1])
        c0_3 = (c0_2[0] + req_depth * n_in[0], c0_2[1] + req_depth * n_in[1])
        c0_4 = (p0[0] + req_depth * n_in[0], p0[1] + req_depth * n_in[1])
        poly0 = Polygon([c0_1, c0_2, c0_3, c0_4])

        # Corner 1 candidate
        c1_1 = (p1[0] - req_width * u[0], p1[1] - req_width * u[1])
        c1_2 = p1
        c1_3 = (p1[0] + req_depth * n_in[0], p1[1] + req_depth * n_in[1])
        c1_4 = (c1_1[0] + req_depth * n_in[0], c1_1[1] + req_depth * n_in[1])
        poly1 = Polygon([c1_1, c1_2, c1_3, c1_4])

        candidates = [poly0, poly1] if prefer_corner == 0 else [poly1, poly0]

        for cand in candidates:
            if not cand.is_valid or cand.area < 5.0:
                continue
            # Ensure cand is within inner_polygon
            overlap = inner_polygon.intersection(cand)
            if overlap.is_empty or overlap.area < cand.area * 0.95:
                continue
            cand_valid = ensure_valid(cand)
            rem = ensure_valid(inner_polygon.difference(cand_valid))
            if rem.is_empty or rem.area < 20.0:
                continue
            logger.info(
                "Carved fixed-footprint parking: %.2f sqm (%.2fm x %.2fm) on road side '%s'",
                cand_valid.area, req_width, req_depth, road_side,
            )
            return cand_valid, rem

    return None, inner_polygon


def generate_parking_shutter_door(
    parking_poly: Polygon,
    inner_polygon: Polygon,
    road_side: str,
    facing: str,
    room_id: str = "parking_0",
    door_id: str = "D_shutter",
) -> Optional[dict]:
    """
    Generate an exterior shutter door (>= 2.4m) on the parking room's road-facing exterior wall.
    """
    road_boundary = _road_side_boundary(inner_polygon, road_side, facing)
    contact = None
    if road_boundary is not None and not road_boundary.is_empty:
        try:
            contact = parking_poly.boundary.intersection(road_boundary.buffer(0.08))
        except Exception:
            contact = None

    if contact is None or contact.is_empty or contact.length < 1.0:
        # Fallback to exterior boundary contact
        try:
            contact = parking_poly.boundary.intersection(inner_polygon.boundary.buffer(0.08))
        except Exception:
            contact = None

    if contact is None or contact.is_empty or contact.length < 1.0:
        return None

    # Get linear piece
    if hasattr(contact, "geoms"):
        lines = [g for g in contact.geoms if isinstance(g, LineString) and g.length >= 0.5]
        if not lines:
            return None
        line = max(lines, key=lambda l: l.length)
    elif isinstance(contact, LineString) and contact.length >= 0.5:
        line = contact
    else:
        return None

    mid = line.interpolate(0.5, normalized=True)
    return {
        "id": door_id,
        "type": "shutter",
        "width": PARKING_SHUTTER_WIDTH_M,
        "position": {"x": round(mid.x, 4), "y": round(mid.y, 4)},
        "wall_id": None,
        "from_room": room_id,
        "to_room": None,
    }


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

    # Check road access: parking should touch road-facing boundary
    road_boundary = _road_side_boundary(inner_polygon, road_side, facing)
    road_contact = 0.0
    if road_boundary is not None and not road_boundary.is_empty:
        try:
            contact = parking_poly.boundary.intersection(road_boundary.buffer(0.08))
            if not contact.is_empty:
                road_contact = contact.length
        except Exception:
            road_contact = 0.0

    if road_contact < 0.5:
        # Fallback to general boundary contact
        road_contact = polygon_exterior_contact(parking_poly, inner_polygon, min_length=0.5)

    has_road_access = road_contact >= 1.0

    return {
        "width_m": round(width, 3),
        "length_m": round(length, 3),
        "meets_width": meets_width,
        "meets_length": meets_length,
        "meets_minimum": meets_width and meets_length,
        "road_access": has_road_access,
        "exterior_contact_m": round(road_contact, 3),
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
