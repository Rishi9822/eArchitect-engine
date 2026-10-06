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
   - Exterior segments are **split at every intersection with an internal room boundary**
     so that each segment belongs to exactly one room (`room_a`).
   - Collinear merging is applied **only** to segments of the same room.
3. A perimeter conservation assertion ensures that the sum of exterior wall
   segment lengths ≈ buildable perimeter length (within tolerance).
4. Every wall segment is assigned a deterministic sequential ID (W001, W002, ...).
"""
from __future__ import annotations

import math
import logging
from itertools import combinations
from typing import List, Tuple, Dict, Optional, Set

from shapely.geometry import (
    Polygon,
    LineString,
    MultiLineString,
    GeometryCollection,
    Point as ShapelyPoint,
)
from shapely.ops import linemerge, split

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

# Tolerance for perimeter conservation assertion (metres)
_PERIMETER_CONSERVATION_TOL = 0.5


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
# EXTERIOR WALL SPLITTING AT ROOM BOUNDARIES
# ─────────────────────────────────────────────

def _collect_interior_split_points(
    room_polygons: List[Polygon],
    boundary_ring,
) -> List[ShapelyPoint]:
    """
    Collect all points where internal room boundaries intersect the
    buildable perimeter.  These become split points for exterior walls.
    """
    split_pts: List[ShapelyPoint] = []
    seen_snapped: Set[Tuple[float, float]] = set()

    for poly in room_polygons:
        if poly.is_empty or not poly.is_valid:
            continue
        try:
            inters = poly.boundary.intersection(boundary_ring)
        except Exception:
            continue

        # Walk through all point-like pieces of the intersection
        def _add_points(geom):
            if geom is None or geom.is_empty:
                return
            if isinstance(geom, ShapelyPoint):
                key = (_snap_coord(geom.x), _snap_coord(geom.y))
                if key not in seen_snapped:
                    seen_snapped.add(key)
                    split_pts.append(geom)
            elif hasattr(geom, "geoms"):
                for g in geom.geoms:
                    _add_points(g)
            elif isinstance(geom, LineString):
                for c in geom.coords:
                    pt = ShapelyPoint(c)
                    key = (_snap_coord(pt.x), _snap_coord(pt.y))
                    if key not in seen_snapped:
                        seen_snapped.add(key)
                        split_pts.append(pt)

        _add_points(inters)

    return split_pts


def _split_segment_at_points(
    seg: LineString,
    split_points: List[ShapelyPoint],
    snap_tol: float = SEGMENT_SNAP_TOLERANCE,
) -> List[LineString]:
    """
    Split a LineString at a set of points that lie (within tolerance) on it.
    Returns a list of sub-segments in order along the original segment.
    """
    if not split_points:
        return [seg]

    # Collect parameter values (0-1 normalised distance along seg)
    params: List[float] = []
    for pt in split_points:
        d = seg.distance(pt)
        if d > snap_tol * 5:
            continue
        t = seg.project(pt, normalized=True)
        # Skip split points that are at the very start/end (within tolerance)
        if t < 1e-6 or t > 1.0 - 1e-6:
            continue
        params.append(t)

    if not params:
        return [seg]

    params = sorted(set(params))

    # Build sub-segments
    sub_segs: List[LineString] = []
    prev_t = 0.0
    coords_list = list(seg.coords)
    start_coord = coords_list[0]

    for t in params:
        pt = seg.interpolate(t, normalized=True)
        sub = LineString([start_coord, (pt.x, pt.y)])
        if sub.length >= MIN_WALL_LENGTH:
            sub_segs.append(sub)
        start_coord = (pt.x, pt.y)
        prev_t = t

    # Final sub-segment
    end_coord = coords_list[-1]
    sub = LineString([start_coord, end_coord])
    if sub.length >= MIN_WALL_LENGTH:
        sub_segs.append(sub)

    return sub_segs if sub_segs else [seg]


def _assign_room_to_segment(
    seg: LineString,
    room_polygons: List[Polygon],
    room_ids: List[str],
) -> Optional[str]:
    """
    Determine which room owns a given exterior wall segment by checking
    which room's boundary most overlaps with the segment.
    """
    mid = seg.interpolate(0.5, normalized=True)
    best_rid = None
    best_dist = float("inf")

    for idx, poly in enumerate(room_polygons):
        if poly.is_empty or not poly.is_valid:
            continue
        d = poly.boundary.distance(mid)
        if d < best_dist:
            best_dist = d
            best_rid = room_ids[idx]

    return best_rid


# ─────────────────────────────────────────────
# COLLINEAR MERGING (EXTERIOR WALLS ONLY)
# ─────────────────────────────────────────────

def _are_collinear(seg_a: dict, seg_b: dict) -> bool:
    """
    Return True only when two exterior segments are genuinely collinear,
    contiguous, **and belong to the same room**.
    """
    # ── Priority 7: Never merge segments across different rooms ──
    if seg_a.get("room_a") != seg_b.get("room_a"):
        return False

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
    """
    Merge collinear exterior wall fragments **within the same room only**.
    Segments from different rooms are never merged.
    """
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
    - **Priority 7**: Exterior segments are split at every intersection with
      internal room boundaries so each segment belongs to exactly one room.
    - Collinear exterior segments are merged **only** within the same room.

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

    # ── 0. Collect split points (interior boundaries hitting perimeter) ──
    split_points = _collect_interior_split_points(room_polygons, boundary_ring)

    # ── 1. Extract Exterior Walls ─────────────────────────────────────
    raw_exterior_lines: List[Tuple[LineString, str]] = []  # (line, room_id)
    seen_exterior_keys: Set[Tuple] = set()

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

            raw_exterior_lines.append((overlap, rid))

    # ── 1a. Split each exterior line at room-boundary split points ────
    split_exterior_segments: List[dict] = []

    for ext_line, original_rid in raw_exterior_lines:
        sub_segs = _split_segment_at_points(ext_line, split_points)

        for sub in sub_segs:
            if not _is_valid_wall_line(sub):
                continue

            # Re-assign room ownership based on which room actually touches
            # this sub-segment (the original rid may be wrong after splitting).
            assigned_rid = _assign_room_to_segment(sub, room_polygons, room_ids)
            if assigned_rid is None:
                assigned_rid = original_rid

            key = _normalise_endpoints(sub)
            if key in seen_exterior_keys:
                continue
            seen_exterior_keys.add(key)

            ov_coords = list(sub.coords)
            start_pt = ov_coords[0]
            end_pt = ov_coords[-1]
            geom_length = math.hypot(end_pt[0] - start_pt[0], end_pt[1] - start_pt[1])
            if geom_length < MIN_WALL_LENGTH:
                continue

            split_exterior_segments.append({
                "start": {"x": round(start_pt[0], 4), "y": round(start_pt[1], 4)},
                "end": {"x": round(end_pt[0], 4), "y": round(end_pt[1], 4)},
                "type": "exterior",
                "thickness": EXTERIOR_WALL_THICKNESS,
                "length": round(geom_length, 4),
                "bearing_deg": round(line_bearing(sub), 1),
                "orientation": line_orientation(sub),
                "room_a": assigned_rid,
                "room_b": None,
            })

    # ── 1b. Apply safe collinear merging (same room only) ─────────────
    clean_exterior_segments = _merge_exterior_collinear_segments(split_exterior_segments)

    # ── 1c. Perimeter conservation assertion ──────────────────────────
    ext_total_len = sum(s["length"] for s in clean_exterior_segments)
    perimeter_len = boundary_ring.length
    if abs(ext_total_len - perimeter_len) > _PERIMETER_CONSERVATION_TOL:
        logger.warning(
            "Perimeter conservation warning: exterior wall sum=%.4f m vs "
            "perimeter=%.4f m (delta=%.4f m, tol=%.1f m)",
            ext_total_len, perimeter_len,
            abs(ext_total_len - perimeter_len),
            _PERIMETER_CONSERVATION_TOL,
        )

    # ── 2. Extract Interior Walls (Pairwise Room Boundary Intersection) ──
    interior_segments: List[dict] = []
    seen_interior_keys: Set[Tuple] = set()

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
