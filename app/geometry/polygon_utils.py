"""
Shared polygon utility functions.

Geometry helpers used across BSP, wall extraction, and architectural
element placement.
"""
from __future__ import annotations

import math
import logging
from typing import List, Tuple, Optional

from shapely.geometry import Polygon, LineString, MultiPolygon
from shapely.ops import split, unary_union

from ..config import (
    MIN_POLYGON_AREA_SQM,
    MAX_ASPECT_RATIO,
    MIN_SPLIT_RATIO,
    MAX_SPLIT_RATIO,
    BSP_RATIO_SEARCH_STEP,
)
from .normalization import ensure_valid

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# MEASUREMENTS
# ─────────────────────────────────────────────

def aspect_ratio(poly: Polygon) -> float:
    """
    Bounding-box aspect ratio (always ≥ 1.0).

    Uses minimum rotated rectangle for more accuracy with rotated rooms.
    """
    try:
        rect = poly.minimum_rotated_rectangle
        coords = list(rect.exterior.coords)
        edge1 = math.sqrt(
            (coords[1][0] - coords[0][0]) ** 2 +
            (coords[1][1] - coords[0][1]) ** 2
        )
        edge2 = math.sqrt(
            (coords[2][0] - coords[1][0]) ** 2 +
            (coords[2][1] - coords[1][1]) ** 2
        )
        w, h = max(edge1, edge2), min(edge1, edge2)
    except Exception:
        minx, miny, maxx, maxy = poly.bounds
        w = maxx - minx
        h = maxy - miny

    if h < 1e-6:
        return float("inf")
    return w / h


def min_dimension(poly: Polygon) -> float:
    """
    Estimate the minimum width/depth of a polygon.

    Uses the shorter side of the minimum rotated rectangle.
    """
    try:
        rect = poly.minimum_rotated_rectangle
        coords = list(rect.exterior.coords)
        edge1 = math.sqrt(
            (coords[1][0] - coords[0][0]) ** 2 +
            (coords[1][1] - coords[0][1]) ** 2
        )
        edge2 = math.sqrt(
            (coords[2][0] - coords[1][0]) ** 2 +
            (coords[2][1] - coords[1][1]) ** 2
        )
        return min(edge1, edge2)
    except Exception:
        minx, miny, maxx, maxy = poly.bounds
        return min(maxx - minx, maxy - miny)


def max_dimension(poly: Polygon) -> float:
    """Estimate the maximum width/depth of a polygon."""
    try:
        rect = poly.minimum_rotated_rectangle
        coords = list(rect.exterior.coords)
        edge1 = math.sqrt(
            (coords[1][0] - coords[0][0]) ** 2 +
            (coords[1][1] - coords[0][1]) ** 2
        )
        edge2 = math.sqrt(
            (coords[2][0] - coords[1][0]) ** 2 +
            (coords[2][1] - coords[1][1]) ** 2
        )
        return max(edge1, edge2)
    except Exception:
        minx, miny, maxx, maxy = poly.bounds
        return max(maxx - minx, maxy - miny)


# ─────────────────────────────────────────────
# SPLITTING
# ─────────────────────────────────────────────

def compute_longest_axis(polygon: Polygon) -> str:
    """
    Determine dominant split axis from the bounding box.

    Returns:
        'x' — split with a horizontal line (cuts top/bottom)
        'y' — split with a vertical line (cuts left/right)
    """
    minx, miny, maxx, maxy = polygon.bounds
    width = maxx - minx
    height = maxy - miny
    return "y" if width > height else "x"


def build_split_line(polygon: Polygon, axis: str, ratio: float) -> LineString:
    """
    Build a LineString that bisects the polygon's bounding box
    at the given ratio along the chosen axis.
    """
    minx, miny, maxx, maxy = polygon.bounds
    pad = max(maxx - minx, maxy - miny) * 2

    if axis == "y":
        split_x = minx + ratio * (maxx - minx)
        return LineString([(split_x, miny - pad), (split_x, maxy + pad)])
    else:
        split_y = miny + ratio * (maxy - miny)
        return LineString([(minx - pad, split_y), (maxx + pad, split_y)])


def split_polygon(
    polygon: Polygon, axis: str, ratio: float
) -> Tuple[Optional[Polygon], Optional[Polygon]]:
    """
    Split a polygon along the given axis at the given ratio.

    Returns two polygons (left/bottom, right/top) or (None, None) on failure.
    """
    try:
        line = build_split_line(polygon, axis, ratio)
        result = split(polygon, line)

        parts = [
            g for g in result.geoms
            if isinstance(g, Polygon) and g.area >= MIN_POLYGON_AREA_SQM
        ]

        if len(parts) < 2:
            return None, None

        # Sort by coordinate for deterministic ordering
        if axis == "y":
            parts.sort(key=lambda g: g.centroid.x)
        else:
            parts.sort(key=lambda g: g.centroid.y)

        # Merge extra fragments with nearest part
        if len(parts) > 2:
            left = unary_union(parts[: len(parts) // 2])
            right = unary_union(parts[len(parts) // 2:])
            parts = [left, right]

        return ensure_valid(parts[0]), ensure_valid(parts[1])

    except Exception as exc:
        logger.debug("split_polygon failed: %s", exc)
        return None, None


def find_best_ratio(
    polygon: Polygon,
    axis: str,
    target_ratio: float,
    max_aspect: float = MAX_ASPECT_RATIO,
) -> float:
    """
    Search for a split ratio near target_ratio that produces
    two valid polygons with acceptable aspect ratios.
    """
    candidates = [target_ratio]
    step = BSP_RATIO_SEARCH_STEP
    for delta in [0, step, -step, step * 2, -step * 2, step * 3, -step * 3]:
        r = target_ratio + delta
        if MIN_SPLIT_RATIO <= r <= MAX_SPLIT_RATIO:
            candidates.append(r)

    for ratio in candidates:
        left, right = split_polygon(polygon, axis, ratio)
        if left is None or right is None:
            continue
        if aspect_ratio(left) <= max_aspect and aspect_ratio(right) <= max_aspect:
            return ratio

    return 0.5


# ─────────────────────────────────────────────
# BOUNDARY & EDGE HELPERS
# ─────────────────────────────────────────────

def polygon_edges(poly: Polygon) -> List[LineString]:
    """Return all edges of a polygon exterior as LineString objects."""
    coords = list(poly.exterior.coords)
    edges = []
    for i in range(len(coords) - 1):
        seg = LineString([coords[i], coords[i + 1]])
        if seg.length >= 1e-6:
            edges.append(seg)
    return edges


def polygons_share_boundary(a: Polygon, b: Polygon, min_length: float = 0.01) -> bool:
    """Check if two polygons share a boundary of at least min_length."""
    try:
        inters = a.boundary.intersection(b.boundary)
        if inters.is_empty:
            return False
        return inters.length >= min_length
    except Exception:
        return False


def polygon_exterior_contact(
    room_poly: Polygon,
    boundary_poly: Polygon,
    min_length: float = 0.5,
) -> float:
    """
    Return the length of the room polygon's exterior that lies
    on the boundary polygon's exterior.
    """
    try:
        room_boundary = room_poly.boundary
        plot_boundary = boundary_poly.boundary
        contact = room_boundary.intersection(plot_boundary.buffer(0.05))
        if contact.is_empty:
            return 0.0
        return contact.length
    except Exception:
        return 0.0


def line_bearing(line: LineString) -> float:
    """
    Compute bearing of a line segment in degrees (0-360, from north/+Y axis).
    """
    coords = list(line.coords)
    dx = coords[-1][0] - coords[0][0]
    dy = coords[-1][1] - coords[0][1]
    bearing = math.degrees(math.atan2(dx, dy)) % 360
    return bearing


def line_orientation(line: LineString, tolerance_deg: float = 10.0) -> str:
    """
    Classify a line as 'horizontal', 'vertical', or 'diagonal'.
    """
    bearing = line_bearing(line)
    # Normalize to 0-180 range
    norm = bearing % 180
    if norm < tolerance_deg or norm > (180 - tolerance_deg):
        return "vertical"
    if abs(norm - 90) < tolerance_deg:
        return "horizontal"
    return "diagonal"
