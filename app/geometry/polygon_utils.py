"""
Shared polygon utility functions.

Geometry helpers used across BSP, wall extraction, and architectural
element placement.
"""
from __future__ import annotations

import math
import logging
from typing import List, Tuple, Optional, Union

from shapely.geometry import Polygon, LineString, MultiPolygon
from shapely.ops import split, unary_union, polylabel

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


def build_split_line(polygon: Polygon, axis: Union[str, float], ratio: float) -> LineString:
    """
    Build a LineString that bisects the polygon's bounding box
    at the given ratio along the chosen axis or bearing angle.

    Args:
        polygon: Polygon to split
        axis: 'x' (horizontal cut), 'y' (vertical cut), or float (bearing angle in degrees 0-360)
        ratio: fraction along the perpendicular axis [0..1]
    """
    minx, miny, maxx, maxy = polygon.bounds
    pad = max(maxx - minx, maxy - miny) * 2

    if axis == "y":
        split_x = minx + ratio * (maxx - minx)
        return LineString([(split_x, miny - pad), (split_x, maxy + pad)])
    elif axis == "x":
        split_y = miny + ratio * (maxy - miny)
        return LineString([(minx - pad, split_y), (maxx + pad, split_y)])
    else:
        # axis represents a bearing angle in degrees (0-360)
        try:
            bearing_deg = float(axis)
        except (ValueError, TypeError):
            split_y = miny + ratio * (maxy - miny)
            return LineString([(minx - pad, split_y), (maxx + pad, split_y)])

        bearing_rad = math.radians(bearing_deg)
        # Vector along bearing: 0° = North (+Y), 90° = East (+X)
        dx = math.sin(bearing_rad)
        dy = math.cos(bearing_rad)
        # Normal vector perpendicular to bearing direction
        nx = -dy
        ny = dx

        coords = list(polygon.exterior.coords)
        projs = [x * nx + y * ny for x, y in coords]
        min_p = min(projs)
        max_p = max(projs)
        target_p = min_p + ratio * (max_p - min_p)

        # Base point on the split plane
        p0_x = target_p * nx
        p0_y = target_p * ny
        return LineString([
            (p0_x - pad * dx, p0_y - pad * dy),
            (p0_x + pad * dx, p0_y + pad * dy),
        ])


def split_polygon(
    polygon: Polygon, axis: Union[str, float], ratio: float
) -> Tuple[Optional[Polygon], Optional[Polygon]]:
    """
    Split a polygon along the given axis or bearing angle at the given ratio.

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
        elif axis == "x":
            parts.sort(key=lambda g: g.centroid.y)
        else:
            try:
                bearing_rad = math.radians(float(axis))
                nx = -math.cos(bearing_rad)
                ny = math.sin(bearing_rad)
                parts.sort(key=lambda g: g.centroid.x * nx + g.centroid.y * ny)
            except Exception:
                parts.sort(key=lambda g: (g.centroid.x, g.centroid.y))

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
    axis: Union[str, float],
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


# ─────────────────────────────────────────────
# PRIORITY 9: IRREGULAR PLOT & ANGLE HELPERS
# ─────────────────────────────────────────────

def get_polygon_internal_angles(poly: Polygon) -> List[float]:
    """
    Compute internal angles in degrees for all vertices of a polygon.
    Returns angles in degrees (in [0, 360)).
    For a rectangle, all internal angles are 90.0°.
    """
    if poly is None or poly.is_empty:
        return []
    coords = list(poly.exterior.coords)
    if coords and coords[0] == coords[-1]:
        coords = coords[:-1]
    if len(coords) < 3:
        return []

    # Ensure counter-clockwise ordering
    p = Polygon(coords)
    if not p.exterior.is_ccw:
        coords = coords[::-1]

    n = len(coords)
    angles = []
    for i in range(n):
        x_prev, y_prev = coords[(i - 1) % n]
        x_curr, y_curr = coords[i]
        x_next, y_next = coords[(i + 1) % n]

        v_in_x = x_curr - x_prev
        v_in_y = y_curr - y_prev
        v_out_x = x_next - x_curr
        v_out_y = y_next - y_curr

        cross = v_in_x * v_out_y - v_in_y * v_out_x
        dot = v_in_x * v_out_x + v_in_y * v_out_y
        turn_angle_rad = math.atan2(cross, dot)
        internal_angle = 180.0 - math.degrees(turn_angle_rad)
        angles.append(internal_angle)

    return angles


def is_polygon_orthogonal(poly: Polygon, tolerance_deg: float = 1.0) -> bool:
    """
    Check if a polygon is orthogonal (all non-collinear vertices are right angles 90° or 270°).
    """
    if poly is None or poly.is_empty:
        return True
    angles = get_polygon_internal_angles(poly)
    if not angles:
        return True
    for ang in angles:
        is_right = (
            abs(ang - 90.0) <= tolerance_deg
            or abs(ang - 180.0) <= tolerance_deg
            or abs(ang - 270.0) <= tolerance_deg
        )
        if not is_right:
            return False
    return True


def min_polygon_internal_angle(poly: Polygon, ignore_collinear: bool = True) -> float:
    """
    Return the minimum internal angle of the polygon in degrees.
    For an orthogonal polygon / rectangle, returns 90.0.
    """
    if poly is None or poly.is_empty:
        return 90.0
    angles = get_polygon_internal_angles(poly)
    if not angles:
        return 90.0
    if ignore_collinear:
        non_collinear = [a for a in angles if abs(a - 180.0) > 1.0]
        if non_collinear:
            return round(min(non_collinear), 2)
    return round(min(angles), 2)


def compute_inscribed_circle_diameter(poly: Polygon, tolerance: float = 0.05) -> float:
    """
    Compute maximum inscribed circle diameter using Shapely polylabel.
    """
    try:
        if poly is None or poly.is_empty:
            return 0.0
        pole = polylabel(poly, tolerance=tolerance)
        radius = poly.boundary.distance(pole)
        return max(0.0, 2.0 * radius)
    except Exception:
        return min_dimension(poly)


def get_polygon_edge_bearings(polygon: Polygon, tolerance_deg: float = 5.0) -> List[float]:
    """
    Extract unique non-orthogonal edge bearings from polygon exterior.
    Bearings are normalized to [0, 180) degrees.
    Excludes bearings within tolerance_deg of 0° (vertical) and 90° (horizontal).
    """
    edges = polygon_edges(polygon)
    bearings: List[float] = []
    for edge in edges:
        b = line_bearing(edge) % 180.0
        is_ortho = (
            b < tolerance_deg
            or b > (180.0 - tolerance_deg)
            or abs(b - 90.0) < tolerance_deg
        )
        if not is_ortho:
            if not any(abs(b - existing) < tolerance_deg for existing in bearings):
                bearings.append(round(b, 2))
    return bearings


def clip_acute_corners(
    poly: Polygon, min_angle_deg: float = 60.0, max_cut_m: float = 1.5
) -> Tuple[Polygon, List[Polygon]]:
    """
    Identify acute corners (< min_angle_deg) of a polygon and clip small
    triangular slivers from them.

    Returns:
        (clipped_polygon, list_of_slivers)
    """
    if poly is None or poly.is_empty:
        return poly, []

    coords = list(poly.exterior.coords)
    if coords and coords[0] == coords[-1]:
        coords = coords[:-1]
    if len(coords) < 3:
        return poly, []

    # Ensure counter-clockwise
    p = Polygon(coords)
    if not p.exterior.is_ccw:
        coords = coords[::-1]

    current_poly = poly
    slivers: List[Polygon] = []

    n = len(coords)
    for i in range(n):
        x_prev, y_prev = coords[(i - 1) % n]
        x_curr, y_curr = coords[i]
        x_next, y_next = coords[(i + 1) % n]

        v_in_x = x_curr - x_prev
        v_in_y = y_curr - y_prev
        v_out_x = x_next - x_curr
        v_out_y = y_next - y_curr

        cross = v_in_x * v_out_y - v_in_y * v_out_x
        dot = v_in_x * v_out_x + v_in_y * v_out_y
        turn_angle_rad = math.atan2(cross, dot)
        internal_angle = 180.0 - math.degrees(turn_angle_rad)

        if 1.0 < internal_angle < min_angle_deg:
            # Edge vectors from current point to previous and next vertices
            dx_prev = x_prev - x_curr
            dy_prev = y_prev - y_curr
            dx_next = x_next - x_curr
            dy_next = y_next - y_curr

            l_prev = math.hypot(dx_prev, dy_prev)
            l_next = math.hypot(dx_next, dy_next)
            if l_prev < 1e-4 or l_next < 1e-4:
                continue

            u_prev_x = dx_prev / l_prev
            u_prev_y = dy_prev / l_prev
            u_next_x = dx_next / l_next
            u_next_y = dy_next / l_next

            # Cut distance proportional to edge length
            d = min(max_cut_m, l_prev * 0.35, l_next * 0.35)
            if d < 0.3:
                continue

            pt_prev_cut = (x_curr + u_prev_x * d, y_curr + u_prev_y * d)
            pt_next_cut = (x_curr + u_next_x * d, y_curr + u_next_y * d)

            sliver = Polygon([(x_curr, y_curr), pt_prev_cut, pt_next_cut])
            if sliver.is_valid and sliver.area > 0.05:
                diff = current_poly.difference(sliver)
                if isinstance(diff, Polygon) and diff.is_valid and diff.area >= current_poly.area * 0.7:
                    current_poly = diff
                    slivers.append(sliver)
                elif isinstance(diff, MultiPolygon):
                    parts = sorted(
                        [g for g in diff.geoms if isinstance(g, Polygon)],
                        key=lambda g: g.area,
                        reverse=True,
                    )
                    if parts and parts[0].area >= current_poly.area * 0.7:
                        current_poly = parts[0]
                        slivers.append(sliver)

    return ensure_valid(current_poly), slivers

