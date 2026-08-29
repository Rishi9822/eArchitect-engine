"""
First-class corridor geometry generation.

Corridors are not ordinary rooms — they are explicit circulation
elements carved from the buildable area before room placement.

Two corridor types:
  - central:  strip through the centre of the buildable area
  - side:     strip along one side of the buildable area

Each function returns (corridor_polygon, region_a, region_b)
where the two regions are the remaining buildable areas for
room placement.
"""
from __future__ import annotations

import logging
import random
from typing import Optional, Tuple, List, Dict

from shapely.geometry import Polygon, box, LineString
from shapely.ops import split

from ..config import (
    MIN_CORRIDOR_WIDTH_M,
    PREFERRED_CORRIDOR_WIDTH_M,
    MAX_CORRIDOR_WIDTH_M,
    CORRIDOR_AREA_RATIO,
    MIN_POLYGON_AREA_SQM,
)
from ..geometry.normalization import ensure_valid
from ..geometry.polygon_utils import min_dimension

logger = logging.getLogger(__name__)


def _corridor_width(buildable_area: float, rng: random.Random) -> float:
    """
    Determine corridor width based on buildable area.

    Larger plots can afford wider corridors.
    """
    if buildable_area > 150:
        base = PREFERRED_CORRIDOR_WIDTH_M + 0.2
    elif buildable_area > 80:
        base = PREFERRED_CORRIDOR_WIDTH_M
    else:
        base = MIN_CORRIDOR_WIDTH_M

    # Small deterministic perturbation
    jitter = rng.uniform(-0.1, 0.1)
    width = max(MIN_CORRIDOR_WIDTH_M, min(MAX_CORRIDOR_WIDTH_M, base + jitter))
    return round(width, 2)


def generate_central_corridor(
    inner_polygon: Polygon,
    facing: str = "north",
    rng: Optional[random.Random] = None,
) -> Tuple[Optional[Polygon], Optional[Polygon], Optional[Polygon]]:
    """
    Carve a central corridor strip through the buildable area.

    The corridor runs along the longer axis of the bounding box,
    positioned near the centre.

    Returns:
        (corridor_polygon, region_left, region_right)
        or (None, None, None) if corridor cannot be carved.
    """
    if rng is None:
        rng = random.Random(42)

    minx, miny, maxx, maxy = inner_polygon.bounds
    width_bb = maxx - minx
    height_bb = maxy - miny

    c_width = _corridor_width(inner_polygon.area, rng)

    # Corridor area check
    if c_width * max(width_bb, height_bb) > inner_polygon.area * CORRIDOR_AREA_RATIO * 2:
        c_width = MIN_CORRIDOR_WIDTH_M

    if width_bb >= height_bb:
        # Horizontal corridor (runs left-right)
        center_y = (miny + maxy) / 2
        # Slight offset from center for variety
        offset = rng.uniform(-height_bb * 0.05, height_bb * 0.05)
        center_y += offset

        corridor_box = box(
            minx - 1, center_y - c_width / 2,
            maxx + 1, center_y + c_width / 2,
        )
    else:
        # Vertical corridor (runs top-bottom)
        center_x = (minx + maxx) / 2
        offset = rng.uniform(-width_bb * 0.05, width_bb * 0.05)
        center_x += offset

        corridor_box = box(
            center_x - c_width / 2, miny - 1,
            center_x + c_width / 2, maxy + 1,
        )

    try:
        corridor_poly = inner_polygon.intersection(corridor_box)
        if corridor_poly.is_empty or corridor_poly.area < MIN_POLYGON_AREA_SQM:
            return None, None, None

        corridor_poly = ensure_valid(corridor_poly)

        # Remaining regions
        remainder = inner_polygon.difference(corridor_box)
        if remainder.is_empty:
            return None, None, None

        # Split remainder into two regions
        parts = []
        if hasattr(remainder, "geoms"):
            for g in remainder.geoms:
                if isinstance(g, Polygon) and g.area >= MIN_POLYGON_AREA_SQM:
                    parts.append(ensure_valid(g))
        elif isinstance(remainder, Polygon) and remainder.area >= MIN_POLYGON_AREA_SQM:
            parts.append(ensure_valid(remainder))

        if len(parts) < 2:
            # Corridor carved too aggressively — try narrower
            if c_width > MIN_CORRIDOR_WIDTH_M:
                return generate_central_corridor(
                    inner_polygon, facing,
                    random.Random(rng.randint(0, 999999)),
                )
            return None, None, None

        # Sort deterministically
        if width_bb >= height_bb:
            parts.sort(key=lambda p: p.centroid.y)
        else:
            parts.sort(key=lambda p: p.centroid.x)

        # Merge extras if more than 2
        if len(parts) > 2:
            from shapely.ops import unary_union
            region_a = unary_union(parts[:len(parts) // 2])
            region_b = unary_union(parts[len(parts) // 2:])
            region_a = ensure_valid(region_a)
            region_b = ensure_valid(region_b)
        else:
            region_a, region_b = parts[0], parts[1]

        return corridor_poly, region_a, region_b

    except Exception as exc:
        logger.warning("Central corridor generation failed: %s", exc)
        return None, None, None


def generate_side_corridor(
    inner_polygon: Polygon,
    facing: str = "north",
    rng: Optional[random.Random] = None,
) -> Tuple[Optional[Polygon], Optional[Polygon], Optional[Polygon]]:
    """
    Carve a corridor strip along one side of the buildable area.

    The corridor is placed along the side opposite to the entrance
    (facing side), or along the longer side.

    Returns:
        (corridor_polygon, main_region, None)
        or (None, None, None) if corridor cannot be carved.
    """
    if rng is None:
        rng = random.Random(42)

    minx, miny, maxx, maxy = inner_polygon.bounds
    width_bb = maxx - minx
    height_bb = maxy - miny

    c_width = _corridor_width(inner_polygon.area, rng)

    # Determine which side to place corridor
    # Place on the side that creates a long, narrow strip
    if width_bb >= height_bb:
        # Corridor along the right side (vertical strip)
        side_choice = rng.choice(["right", "left"])
        if side_choice == "right":
            corridor_box = box(
                maxx - c_width, miny - 1,
                maxx + 1, maxy + 1,
            )
        else:
            corridor_box = box(
                minx - 1, miny - 1,
                minx + c_width, maxy + 1,
            )
    else:
        # Corridor along the top or bottom (horizontal strip)
        side_choice = rng.choice(["top", "bottom"])
        if side_choice == "top":
            corridor_box = box(
                minx - 1, maxy - c_width,
                maxx + 1, maxy + 1,
            )
        else:
            corridor_box = box(
                minx - 1, miny - 1,
                maxx + 1, miny + c_width,
            )

    try:
        corridor_poly = inner_polygon.intersection(corridor_box)
        if corridor_poly.is_empty or corridor_poly.area < MIN_POLYGON_AREA_SQM:
            return None, None, None

        corridor_poly = ensure_valid(corridor_poly)

        # Remaining region for rooms
        main_region = inner_polygon.difference(corridor_box)
        if main_region.is_empty or main_region.area < MIN_POLYGON_AREA_SQM:
            return None, None, None

        # Consolidate into single polygon
        if hasattr(main_region, "geoms"):
            parts = [
                g for g in main_region.geoms
                if isinstance(g, Polygon) and g.area >= MIN_POLYGON_AREA_SQM
            ]
            if not parts:
                return None, None, None
            from shapely.ops import unary_union
            main_region = ensure_valid(unary_union(parts))
        else:
            main_region = ensure_valid(main_region)

        return corridor_poly, main_region, None

    except Exception as exc:
        logger.warning("Side corridor generation failed: %s", exc)
        return None, None, None


def build_corridor_data(
    corridor_poly: Polygon,
    room_polygons: Dict[str, Polygon],
    corridor_id: str = "corridor_0",
) -> dict:
    """
    Build a corridor output dict from its polygon.

    Determines which rooms the corridor connects to by checking
    shared boundaries.
    """
    from ..geometry.polygon_utils import polygons_share_boundary

    connected = []
    for room_id, room_poly in room_polygons.items():
        if polygons_share_boundary(corridor_poly, room_poly, min_length=0.1):
            connected.append(room_id)

    # Estimate width and length from minimum rotated rectangle
    try:
        rect = corridor_poly.minimum_rotated_rectangle
        coords = list(rect.exterior.coords)
        import math
        edge1 = math.sqrt(
            (coords[1][0] - coords[0][0]) ** 2 +
            (coords[1][1] - coords[0][1]) ** 2
        )
        edge2 = math.sqrt(
            (coords[2][0] - coords[1][0]) ** 2 +
            (coords[2][1] - coords[1][1]) ** 2
        )
        c_width = round(min(edge1, edge2), 3)
        c_length = round(max(edge1, edge2), 3)
    except Exception:
        c_width = 1.2
        c_length = corridor_poly.area / c_width

    centroid = corridor_poly.centroid
    poly_coords = [
        {"x": round(x, 4), "y": round(y, 4)}
        for x, y in list(corridor_poly.exterior.coords)[:-1]
    ]

    return {
        "id": corridor_id,
        "type": "corridor",
        "polygon": poly_coords,
        "centroid": {"x": round(centroid.x, 4), "y": round(centroid.y, 4)},
        "area_sqm": round(corridor_poly.area, 4),
        "width": c_width,
        "length": c_length,
        "connected_rooms": connected,
        "entrance_connection": True if connected else False,
    }
