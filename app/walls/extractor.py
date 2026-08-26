"""
Enhanced Wall Segment Extraction System.

Extracts a clean, non-overlapping, topologically valid wall graph:
1. Interior walls are derived strictly from pairwise room boundary intersections:
   `shared = room_a.boundary.intersection(room_b.boundary)`
   - Only 1D linear intersections (LineString / MultiLineString) with length >= MIN_WALL_LENGTH are kept.
   - Point / corner intersections are discarded.
   - Every interior wall has `room_a` and `room_b` corresponding to the actual rooms sharing that boundary.
   - No duplicate, reverse, or overlapping interior walls are created.
2. Exterior walls are derived from room boundaries lying on the buildable perimeter.
   - Collinear merging is safely applied to exterior walls.
3. Every wall segment is assigned a deterministic sequential ID (W001, W002, ...).
"""
from __future__ import annotations

import math
import logging
from itertools import combinations
from typing import List, Tuple, Dict, Optional

from shapely.geometry import (
    Polygon,
    LineString,
    MultiLineString,
    GeometryCollection,
    Point as ShapelyPoint,
)
from shapely.ops import linemerge

from ..config import (
    EXTERIOR_WALL_THICKNESS,
    INTERIOR_WALL_THICKNESS,
    SEGMENT_SNAP_TOLERANCE,
    MIN_WALL_LENGTH,
    BOUNDARY_BUFFER,
    COLLINEAR_ANGLE_TOLERANCE,
    COLLINEAR_GAP_TOLERANCE,
)
from ..geometry.polygon_utils import line_bearing, line_orientation

logger = logging.getLogger(__name__)


def _is_valid_wall_line(line: LineString) -> bool:
    """Return True only for a non-degenerate wall segment with sufficient length."""
    if line is None or line.is_empty:
        return False

    if not isinstance(line, LineString):
        return False

    if len(line.coords) < 2:
        return False

    if line.length < MIN_WALL_LENGTH:
        return False

    start = line.coords[0]
    end = line.coords[-1]

    dx = end[0] - start[0]
    dy = end[1] - start[1]

    return math.hypot(dx, dy) >= MIN_WALL_LENGTH


def _snap_coord(v: float) -> float:
    return round(v / SEGMENT_SNAP_TOLERANCE) * SEGMENT_SNAP_TOLERANCE


def _normalise_endpoints(
    line: LineString,
) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """Canonical form of a segment for deduplication."""
    coords = list(line.coords)
    a = (_snap_coord(coords[0][0]), _snap_coord(coords[0][1]))
    b = (_snap_coord(coords[-1][0]), _snap_coord(coords[-1][1]))
    return (a, b) if a <= b else (b, a)


def _extract_linear_parts(geom) -> List[LineString]:
    """Extract all valid straight LineString parts from any Shapely geometry."""
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, LineString):
        if geom.length < MIN_WALL_LENGTH:
            return []
        # If line has multiple segments, decompose into straight segments if needed
        coords = list(geom.coords)
        if len(coords) <= 2:
            return [geom]
        # Check if entire line is straight
        start = coords[0]
        end = coords[-1]
        straight_len = math.hypot(end[0] - start[0], end[1] - start[1])
        if abs(straight_len - geom.length) < 1e-4:
            return [LineString([start, end])]
        # Decompose segment by segment
        segments = []
        for i in range(len(coords) - 1):
            seg = LineString([coords[i], coords[i + 1]])
            if seg.length >= MIN_WALL_LENGTH:
                segments.append(seg)
        return segments
    if isinstance(geom, (MultiLineString, GeometryCollection)):
        result = []
        for g in geom.geoms:
            result.extend(_extract_linear_parts(g))
        return result
    return []


# ─────────────────────────────────────────────
# EXTERIOR BOUNDARY MEMBERSHIP TEST
# ─────────────────────────────────────────────

def _segment_on_boundary(
    segment: LineString, boundary_ring
) -> Optional[LineString]:
    """
    Return the portion of segment that lies on boundary_ring.
    Uses a small buffer to absorb floating-point tolerances.
    """
    try:
        buffered = boundary_ring.buffer(BOUNDARY_BUFFER)
        overlap = segment.intersection(buffered)
        linear = _extract_linear_parts(overlap)
        if not linear:
            return None
        merged = linemerge(linear) if len(linear) > 1 else linear[0]
        if merged.is_empty or merged.length < MIN_WALL_LENGTH:
            return None
        if isinstance(merged, MultiLineString):
            merged = max(merged.geoms, key=lambda g: g.length)
        return merged if isinstance(merged, LineString) and _is_valid_wall_line(merged) else None
    except Exception as exc:
        logger.debug("Boundary test failed: %s", exc)
        return None


# ─────────────────────────────────────────────
# COLLINEAR MERGING (EXTERIOR WALLS ONLY)
# ─────────────────────────────────────────────

def _are_collinear(seg_a: dict, seg_b: dict) -> bool:
    """Return True only when two exterior segments are genuinely collinear and contiguous."""
    line_a = LineString([
        (seg_a["start"]["x"], seg_a["start"]["y"]),
        (seg_a["end"]["x"], seg_a["end"]["y"]),
    ])
    line_b = LineString([
        (seg_b["start"]["x"], seg_b["start"]["y"]),
        (seg_b["end"]["x"], seg_b["end"]["y"]),
    ])

    if not _is_valid_wall_line(line_a) or not _is_valid_wall_line(line_b):
        return False

    if seg_a.get("type") != "exterior" or seg_b.get("type") != "exterior":
        return False

    # Check bearing similarity
    bearing_a = line_bearing(line_a) % 180.0
    bearing_b = line_bearing(line_b) % 180.0

    diff = abs(bearing_a - bearing_b)
    diff = min(diff, 180.0 - diff)

    if diff > COLLINEAR_ANGLE_TOLERANCE:
        return False

    # Proximity check
    a0 = ShapelyPoint(line_a.coords[0])
    a1 = ShapelyPoint(line_a.coords[-1])
    b0 = ShapelyPoint(line_b.coords[0])
    b1 = ShapelyPoint(line_b.coords[-1])

    if a0.distance(line_b) > COLLINEAR_GAP_TOLERANCE and a1.distance(line_b) > COLLINEAR_GAP_TOLERANCE:
        return False

    if b0.distance(line_a) > COLLINEAR_GAP_TOLERANCE and b1.distance(line_a) > COLLINEAR_GAP_TOLERANCE:
        return False

    # Must be close to each other
    if line_a.distance(line_b) > COLLINEAR_GAP_TOLERANCE:
        return False

    return True


def _merge_two_exterior_segments(seg_a: dict, seg_b: dict) -> dict:
    """Merge two collinear exterior segments."""
    line_a = LineString([
        (seg_a["start"]["x"], seg_a["start"]["y"]),
        (seg_a["end"]["x"], seg_a["end"]["y"]),
    ])
    line_b = LineString([
        (seg_b["start"]["x"], seg_b["start"]["y"]),
        (seg_b["end"]["x"], seg_b["end"]["y"]),
    ])

    merged = linemerge([line_a, line_b])

    if isinstance(merged, LineString) and _is_valid_wall_line(merged):
        coords = list(merged.coords)
    else:
        endpoints = [
            line_a.coords[0], line_a.coords[-1],
            line_b.coords[0], line_b.coords[-1],
        ]
        max_dist = -1.0
        best_pair = (endpoints[0], endpoints[-1])
        for i in range(len(endpoints)):
            for j in range(i + 1, len(endpoints)):
                d = math.hypot(endpoints[i][0] - endpoints[j][0], endpoints[i][1] - endpoints[j][1])
                if d > max_dist:
                    max_dist = d
                    best_pair = (endpoints[i], endpoints[j])
        coords = [best_pair[0], best_pair[1]]

    merged_line = LineString(coords)
    start_pt = coords[0]
    end_pt = coords[-1]
    geom_length = math.hypot(end_pt[0] - start_pt[0], end_pt[1] - start_pt[1])

    return {
        "start": {"x": round(start_pt[0], 4), "y": round(start_pt[1], 4)},
        "end": {"x": round(end_pt[0], 4), "y": round(end_pt[1], 4)},
        "type": "exterior",
        "thickness": EXTERIOR_WALL_THICKNESS,
        "length": round(geom_length, 4),
        "bearing_deg": round(line_bearing(merged_line), 1),
        "orientation": line_orientation(merged_line),
        "room_a": seg_a.get("room_a") or seg_b.get("room_a"),
        "room_b": None,
    }


def _merge_exterior_collinear_segments(segments: List[dict]) -> List[dict]:
    """Merge collinear exterior wall fragments."""
    if len(segments) <= 1:
        return segments

    merged = True
    result = list(segments)

    while merged:
        merged = False
        new_result = []
        used = set()

        for i in range(len(result)):
            if i in used:
                continue
            current = result[i]
            for j in range(i + 1, len(result)):
                if j in used:
                    continue
                if _are_collinear(current, result[j]):
                    current = _merge_two_exterior_segments(current, result[j])
                    used.add(j)
                    merged = True
            new_result.append(current)
        result = new_result

    return result


# ─────────────────────────────────────────────
# CORE EXTRACTION PIPELINE
# ─────────────────────────────────────────────

def extract_wall_segments(
    room_polygons: List[Polygon],
    room_ids: List[str],
    plot_polygon: Polygon,
    inner_polygon: Optional[Polygon] = None,
) -> List[dict]:
    """
    Extract a unified, classified, topologically valid wall graph from room polygons.

    Interior walls:
    - Derived strictly from `room_a.boundary.intersection(room_b.boundary)`
    - Evaluated over unique pairs (i < j) to guarantee zero duplicates/reverses
    - Only 1D linear pieces >= MIN_WALL_LENGTH are extracted
    - Preserves exact room relationships (room_a, room_b)
    - Zero interior overlap

    Exterior walls:
    - Derived from room edges that lie on the buildable perimeter
    - Collinear exterior segments are cleanly merged

    Args:
        room_polygons: list of room Shapely Polygons
        room_ids: list of room ID strings
        plot_polygon: original plot polygon
        inner_polygon: buildable polygon (after setback)

    Returns:
        list of wall segment dicts with id, start, end, type, thickness, length, bearing, orientation, room_a, room_b
    """
    reference_polygon = inner_polygon if inner_polygon is not None else plot_polygon
    boundary_ring = reference_polygon.boundary

    # ── 1. Extract Exterior Walls ─────────────────────────────────────
    exterior_segments: List[dict] = []
    seen_exterior_keys = set()

    for idx, poly in enumerate(room_polygons):
        if poly.is_empty or not poly.is_valid:
            continue
        rid = room_ids[idx]
        coords = list(poly.exterior.coords)

        for k in range(len(coords) - 1):
            edge = LineString([coords[k], coords[k + 1]])
            if edge.length < MIN_WALL_LENGTH:
                continue

            overlap = _segment_on_boundary(edge, boundary_ring)
            if overlap is None or not _is_valid_wall_line(overlap):
                continue

            key = _normalise_endpoints(overlap)
            if key in seen_exterior_keys:
                continue
            seen_exterior_keys.add(key)

            ov_coords = list(overlap.coords)
            start_pt = ov_coords[0]
            end_pt = ov_coords[-1]
            geom_length = math.hypot(end_pt[0] - start_pt[0], end_pt[1] - start_pt[1])
            if geom_length < MIN_WALL_LENGTH:
                continue

            exterior_segments.append({
                "start": {"x": round(start_pt[0], 4), "y": round(start_pt[1], 4)},
                "end": {"x": round(end_pt[0], 4), "y": round(end_pt[1], 4)},
                "type": "exterior",
                "thickness": EXTERIOR_WALL_THICKNESS,
                "length": round(geom_length, 4),
                "bearing_deg": round(line_bearing(overlap), 1),
                "orientation": line_orientation(overlap),
                "room_a": rid,
                "room_b": None,
            })

    # Apply safe collinear merging to exterior walls
    clean_exterior_segments = _merge_exterior_collinear_segments(exterior_segments)

    # ── 2. Extract Interior Walls (Pairwise Room Boundary Intersection) ──
    interior_segments: List[dict] = []
    seen_interior_keys = set()

    n_rooms = len(room_polygons)
    for i in range(n_rooms):
        for j in range(i + 1, n_rooms):
            poly_a = room_polygons[i]
            poly_b = room_polygons[j]

            if poly_a.is_empty or poly_b.is_empty or not poly_a.is_valid or not poly_b.is_valid:
                continue

            if not poly_a.intersects(poly_b):
                continue

            try:
                shared = poly_a.boundary.intersection(poly_b.boundary)
                linear_parts = _extract_linear_parts(shared)

                for line in linear_parts:
                    if not _is_valid_wall_line(line):
                        continue

                    key = _normalise_endpoints(line)
                    if key in seen_interior_keys:
                        continue
                    seen_interior_keys.add(key)

                    l_coords = list(line.coords)
                    start_pt = l_coords[0]
                    end_pt = l_coords[-1]
                    geom_length = math.hypot(end_pt[0] - start_pt[0], end_pt[1] - start_pt[1])
                    if geom_length < MIN_WALL_LENGTH:
                        continue

                    interior_segments.append({
                        "start": {"x": round(start_pt[0], 4), "y": round(start_pt[1], 4)},
                        "end": {"x": round(end_pt[0], 4), "y": round(end_pt[1], 4)},
                        "type": "interior",
                        "thickness": INTERIOR_WALL_THICKNESS,
                        "length": round(geom_length, 4),
                        "bearing_deg": round(line_bearing(line), 1),
                        "orientation": line_orientation(line),
                        "room_a": room_ids[i],
                        "room_b": room_ids[j],
                    })
            except Exception as exc:
                logger.debug("Error computing shared boundary between %s and %s: %s", room_ids[i], room_ids[j], exc)

    # ── 3. Combine and Assign Clean Sequential IDs ───────────────────
    all_walls = clean_exterior_segments + interior_segments

    for idx, wall in enumerate(all_walls):
        wall["id"] = f"W{idx + 1:03d}"

    logger.info(
        "Extracted %d walls (%d exterior, %d interior)",
        len(all_walls), len(clean_exterior_segments), len(interior_segments),
    )

    return all_walls
