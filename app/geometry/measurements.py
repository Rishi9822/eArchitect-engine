"""
Estimator-ready geometric measurements.

Computes all geometric primitives required by the future
eArchitect Platform estimator.  NO material prices, NO cost
calculations — only geometry.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from shapely.geometry import Polygon

from ..config import (
    SQ_M_TO_SQ_FT,
    DEFAULT_FLOOR_HEIGHT_M,
    EXTERIOR_WALL_THICKNESS,
    INTERIOR_WALL_THICKNESS,
)

logger = logging.getLogger(__name__)


def compute_measurements(
    plot_polygon: Polygon,
    inner_polygon: Polygon,
    room_polygons: List[Polygon],
    walls: List[dict],
    doors: List[dict],
    windows: List[dict],
    floor_height_m: float = DEFAULT_FLOOR_HEIGHT_M,
    corridor_polygons: Optional[List[Polygon]] = None,
) -> dict:
    """
    Compute all estimator-ready geometric measurements.

    Args:
        plot_polygon:      original plot (before setback)
        inner_polygon:     buildable area (after setback)
        room_polygons:     list of room Shapely Polygons
        walls:             list of wall dicts with 'type', 'length'
        doors:             list of door dicts
        windows:           list of window dicts
        floor_height_m:    floor-to-ceiling height
        corridor_polygons: optional list of corridor Shapely Polygons

    Returns:
        dict of measurements in both metric and imperial.
    """
    plot_area_sqm = plot_polygon.area
    buildable_area_sqm = inner_polygon.area
    room_area_sqm = sum(p.area for p in room_polygons)

    corridor_area_sqm = 0.0
    if corridor_polygons:
        corridor_area_sqm = sum(p.area for p in corridor_polygons)

    # Built-up area includes rooms + corridors
    built_up_area_sqm = room_area_sqm + corridor_area_sqm

    ext_wall_length = sum(
        w.get("length", 0) for w in walls if w.get("type") == "exterior"
    )
    int_wall_length = sum(
        w.get("length", 0) for w in walls if w.get("type") == "interior"
    )
    total_wall_length = ext_wall_length + int_wall_length

    ext_wall_area = ext_wall_length * floor_height_m
    int_wall_area = int_wall_length * floor_height_m

    perimeter = inner_polygon.length

    return {
        "plot_area_sqm": round(plot_area_sqm, 4),
        "plot_area_sqft": round(plot_area_sqm * SQ_M_TO_SQ_FT, 2),
        "buildable_area_sqm": round(buildable_area_sqm, 4),
        "buildable_area_sqft": round(buildable_area_sqm * SQ_M_TO_SQ_FT, 2),
        "room_area_sqm": round(room_area_sqm, 4),
        "room_area_sqft": round(room_area_sqm * SQ_M_TO_SQ_FT, 2),
        "built_up_area_sqm": round(built_up_area_sqm, 4),
        "built_up_area_sqft": round(built_up_area_sqm * SQ_M_TO_SQ_FT, 2),
        "exterior_wall_length_m": round(ext_wall_length, 4),
        "interior_wall_length_m": round(int_wall_length, 4),
        "total_wall_length_m": round(total_wall_length, 4),
        "exterior_wall_area_sqm": round(ext_wall_area, 4),
        "interior_wall_area_sqm": round(int_wall_area, 4),
        "floor_area_sqm": round(room_area_sqm, 4),
        "floor_area_sqft": round(room_area_sqm * SQ_M_TO_SQ_FT, 2),
        "roof_area_sqm": round(room_area_sqm, 4),
        "roof_area_sqft": round(room_area_sqm * SQ_M_TO_SQ_FT, 2),
        "total_door_count": len(doors),
        "total_window_count": len(windows),
        "perimeter_m": round(perimeter, 4),
        "corridor_area_sqm": round(corridor_area_sqm, 4),
        "corridor_area_sqft": round(corridor_area_sqm * SQ_M_TO_SQ_FT, 2),
    }
