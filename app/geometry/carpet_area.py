"""
Carpet Area, Built-up Area, and Wall Accounting System.

Implements architectural and RERA carpet area accounting:
- Computes true carpet polygons by insetting room boundaries by half of each bounding wall's thickness.
- Separates net carpet area from built-up area and super built-up area (with common corridor loading).
- Enforces geometric conservation:
    sum(carpet_area) + sum(corridor_area) + total_wall_footprint_area == buildable_area (within 0.01 sqm).
- Computes masonry wall volume (metric m³ and imperial cu ft).
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from shapely.geometry import Polygon, LineString, MultiPolygon
from shapely.ops import unary_union

from ..config import (
    EXTERIOR_WALL_THICKNESS,
    INTERIOR_WALL_THICKNESS,
    DEFAULT_FLOOR_HEIGHT_M,
    SQ_M_TO_SQ_FT,
    M3_TO_CU_FT,
)

logger = logging.getLogger(__name__)


def compute_room_carpet_polygon(
    room_poly: Polygon,
    walls: Optional[List[dict]] = None,
    inner_polygon: Optional[Polygon] = None,
) -> Tuple[Polygon, float]:
    """
    Compute the carpet polygon for a single room by insetting each bounding edge
    by half the thickness of its corresponding wall.

    Args:
        room_poly: Shapely Polygon of the room (gross BSP leaf).
        walls: List of wall dicts (with 'start', 'end', 'thickness', 'type').
        inner_polygon: Optional buildable area polygon for exterior edge reference.

    Returns:
        (carpet_polygon, wall_footprint_inside_room)
    """
    if room_poly is None or room_poly.is_empty or not room_poly.is_valid:
        return Polygon(), 0.0

    strips = []

    if walls:
        for w in walls:
            try:
                start = (w["start"]["x"], w["start"]["y"])
                end = (w["end"]["x"], w["end"]["y"])
                w_line = LineString([start, end])
                if w_line.length < 1e-4:
                    continue

                # Check if this wall touches or shares boundary with room_poly
                inter = w_line.intersection(room_poly.buffer(1e-3))
                if not inter.is_empty and inter.length > 1e-4:
                    thickness = float(w.get("thickness", INTERIOR_WALL_THICKNESS))
                    # Half-thickness deduction inside room
                    strip = w_line.buffer(thickness / 2.0, cap_style=2, join_style=2)
                    strips.append(strip)
            except Exception as exc:
                logger.debug("Failed checking wall %s against room polygon: %s", w.get("id"), exc)

    # If no matching walls were found (e.g. isolated test room), deduce default walls
    if not strips:
        coords = list(room_poly.exterior.coords)
        for i in range(len(coords) - 1):
            seg = LineString([coords[i], coords[i + 1]])
            if seg.length < 1e-4:
                continue
            is_exterior = False
            if inner_polygon and not inner_polygon.is_empty:
                try:
                    d = seg.distance(inner_polygon.exterior)
                    if d < 1e-3:
                        is_exterior = True
                except Exception:
                    pass
            t = EXTERIOR_WALL_THICKNESS if is_exterior else INTERIOR_WALL_THICKNESS
            strips.append(seg.buffer(t / 2.0, cap_style=2, join_style=2))

    if strips:
        try:
            wall_union = unary_union(strips)
            carpet = room_poly.difference(wall_union)
        except Exception:
            carpet = room_poly.buffer(-INTERIOR_WALL_THICKNESS / 2.0)
    else:
        carpet = room_poly

    if isinstance(carpet, MultiPolygon):
        valid_geoms = [g for g in carpet.geoms if not g.is_empty and g.is_valid and g.area > 0.01]
        carpet = max(valid_geoms, key=lambda g: g.area) if valid_geoms else Polygon()

    if carpet.is_empty or carpet.area <= 0.0 or not carpet.is_valid:
        # Fallback to mild buffer if difference erased the room
        carpet = room_poly.buffer(-0.02)
        if isinstance(carpet, MultiPolygon):
            carpet = max(carpet.geoms, key=lambda g: g.area) if carpet.geoms else room_poly
        if carpet.is_empty:
            carpet = room_poly

    wall_footprint = max(0.0, room_poly.area - carpet.area)
    return carpet, wall_footprint


def compute_layout_carpet_accounting(
    room_polygons: Dict[str, Polygon],
    walls: List[dict],
    corridors: Optional[List[dict]] = None,
    corridor_polygons: Optional[List[Polygon]] = None,
    dead_spaces: Optional[List[dict]] = None,
    inner_polygon: Optional[Polygon] = None,
    floor_height_m: float = DEFAULT_FLOOR_HEIGHT_M,
) -> dict:
    """
    Perform full carpet area, built-up area, super built-up area, and wall footprint accounting
    across an entire layout candidate.

    Returns:
        dict containing:
        - per_room: Dict[room_id, {carpet_polygon, carpet_area_sqm, built_up_area_sqm, super_built_up_area_sqm, wall_footprint_area_sqm}]
        - total_carpet_area_sqm
        - total_built_up_area_sqm
        - total_super_built_up_area_sqm
        - total_corridor_area_sqm
        - total_dead_space_area_sqm
        - total_wall_footprint_area_sqm
        - masonry_wall_volume_m3
        - masonry_wall_volume_cuft
        - conservation_error_sqm
        - conservation_valid (bool)
    """
    per_room: Dict[str, dict] = {}
    total_room_gross_sqm = 0.0
    total_carpet_sqm = 0.0
    total_room_wall_fp = 0.0

    # 1. Compute per-room carpet polygon and wall footprint
    for room_id, poly in room_polygons.items():
        c_poly, w_fp = compute_room_carpet_polygon(poly, walls, inner_polygon=inner_polygon)
        gross_area = poly.area
        carpet_area = c_poly.area

        per_room[room_id] = {
            "carpet_polygon": c_poly,
            "carpet_area_sqm": carpet_area,
            "built_up_area_sqm": gross_area,
            "wall_footprint_area_sqm": w_fp,
        }
        total_room_gross_sqm += gross_area
        total_carpet_sqm += carpet_area
        total_room_wall_fp += w_fp

    # 2. Corridors and common areas
    total_corridor_sqm = 0.0
    if corridor_polygons:
        total_corridor_sqm = sum(p.area for p in corridor_polygons)
    elif corridors:
        total_corridor_sqm = sum(c.get("area_sqm", 0.0) for c in corridors)

    # 3. Dead spaces
    total_dead_sqm = 0.0
    if dead_spaces:
        total_dead_sqm = sum(d.get("area_sqm", 0.0) for d in dead_spaces)

    # 4. Total built-up & super built-up accounting
    total_built_up_sqm = total_room_gross_sqm + total_corridor_sqm
    total_super_built_up_area_sqm = total_built_up_sqm
    total_super_built_up_sqm = total_built_up_sqm

    # Loading factor for super built-up area distribution per room
    loading_ratio = (
        total_built_up_sqm / total_room_gross_sqm
        if total_room_gross_sqm > 0
        else 1.0
    )

    for room_id, rdata in per_room.items():
        rdata["super_built_up_area_sqm"] = rdata["built_up_area_sqm"] * loading_ratio

    # 5. Wall footprint area: all room wall deductions + dead spaces
    total_wall_footprint_sqm = total_room_wall_fp + total_dead_sqm

    # 6. Masonry wall volume
    wall_volume_m3 = 0.0
    for w in walls:
        l = float(w.get("length", 0.0))
        t = float(w.get("thickness", INTERIOR_WALL_THICKNESS))
        wall_volume_m3 += l * t * floor_height_m

    wall_volume_cuft = wall_volume_m3 * M3_TO_CU_FT

    # 7. Conservation check against buildable area
    buildable_area_sqm = inner_polygon.area if inner_polygon and not inner_polygon.is_empty else total_built_up_sqm + total_dead_sqm
    conservation_sum = total_carpet_sqm + total_corridor_sqm + total_wall_footprint_sqm
    conservation_error = abs(conservation_sum - buildable_area_sqm)
    conservation_valid = conservation_error <= 0.01

    return {
        "per_room": per_room,
        "total_carpet_area_sqm": round(total_carpet_sqm, 4),
        "total_carpet_area_sqft": round(total_carpet_sqm * SQ_M_TO_SQ_FT, 2),
        "total_built_up_area_sqm": round(total_built_up_sqm, 4),
        "total_built_up_area_sqft": round(total_built_up_sqm * SQ_M_TO_SQ_FT, 2),
        "total_super_built_up_area_sqm": round(total_super_built_up_area_sqm, 4),
        "total_super_built_up_area_sqft": round(total_super_built_up_area_sqm * SQ_M_TO_SQ_FT, 2),
        "total_corridor_area_sqm": round(total_corridor_sqm, 4),
        "total_dead_space_area_sqm": round(total_dead_sqm, 4),
        "total_wall_footprint_area_sqm": round(total_wall_footprint_sqm, 4),
        "total_wall_footprint_area_sqft": round(total_wall_footprint_sqm * SQ_M_TO_SQ_FT, 2),
        "masonry_wall_volume_m3": round(wall_volume_m3, 4),
        "masonry_wall_volume_cuft": round(wall_volume_cuft, 2),
        "conservation_sum_sqm": round(conservation_sum, 4),
        "conservation_error_sqm": round(conservation_error, 6),
        "conservation_valid": conservation_valid,
    }
