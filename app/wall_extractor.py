"""
Wall Segment Extraction System.

Converts a set of room polygons into a unified, classified wall graph.

Classification Rules:
─────────────────────────────────────────────────────────────────────────
  EXTERIOR wall:
    Any edge (or edge portion) that lies on the setback-applied inner
    plot boundary (the actual build zone perimeter).
    Thickness: 9 inches = 0.2286 m

  INTERIOR wall:
    Any edge (or edge portion) shared between exactly two room polygons.
    Thickness: 4.5 inches = 0.1143 m
─────────────────────────────────────────────────────────────────────────

Key fix: compare room edges against `inner_polygon` boundary (post-setback),
not the original plot polygon. BSP rooms are carved from inner_polygon,
so their outer edges lie on the inner_polygon boundary — not the original plot.
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
)
from shapely.ops import unary_union, linemerge

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────

EXTERIOR_WALL_THICKNESS = 0.2286   # 9 inches in metres
INTERIOR_WALL_THICKNESS = 0.1143   # 4.5 inches in metres
SEGMENT_SNAP_TOLERANCE  = 0.005    # 5 mm snap tolerance
MIN_WALL_LENGTH         = 0.05     # Ignore sub-50mm segments (numeric noise)
BOUNDARY_BUFFER         = 0.05     # 5 cm buffer for boundary membership test


# ─────────────────────────────────────────────
# LOW-LEVEL GEOMETRY HELPERS
# ─────────────────────────────────────────────

def _coords_to_edges(polygon: Polygon) -> List[LineString]:
    """Return all edges of a polygon exterior ring as LineString objects."""
    coords = list(polygon.exterior.coords)
    edges = []
    for i in range(len(coords) - 1):
        seg = LineString([coords[i], coords[i + 1]])
        if seg.length >= MIN_WALL_LENGTH:
            edges.append(seg)
    return edges


def _snap_coord(v: float) -> float:
    return round(v / SEGMENT_SNAP_TOLERANCE) * SEGMENT_SNAP_TOLERANCE


def _normalise_endpoints(line: LineString) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """
    Canonical form of a segment for deduplication.
    Always orders start < end lexicographically after snapping.
    """
    coords = list(line.coords)
    a = (_snap_coord(coords[0][0]),  _snap_coord(coords[0][1]))
    b = (_snap_coord(coords[-1][0]), _snap_coord(coords[-1][1]))
    return (a, b) if a <= b else (b, a)


def _extract_linear_parts(geom) -> List[LineString]:
    """Extract all LineString parts from any Shapely geometry type."""
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, LineString):
        return [geom] if geom.length >= MIN_WALL_LENGTH else []
    if isinstance(geom, (MultiLineString, GeometryCollection)):
        result = []
        for g in geom.geoms:
            result.extend(_extract_linear_parts(g))
        return result
    return []


def _line_to_dict(line: LineString, wall_type: str, thickness: float) -> dict:
    """Format a LineString as a wall segment dict."""
    coords = list(line.coords)
    start = coords[0]
    end   = coords[-1]
    return {
        "start":     {"x": round(start[0], 4), "y": round(start[1], 4)},
        "end":       {"x": round(end[0],   4), "y": round(end[1],   4)},
        "type":      wall_type,
        "thickness": thickness,
        "length":    round(line.length, 4),
    }


# ─────────────────────────────────────────────
# BOUNDARY MEMBERSHIP TEST
# ─────────────────────────────────────────────

def _segment_on_boundary(segment: LineString, boundary_ring) -> Optional[LineString]:
    """
    Return the portion of `segment` that lies on `boundary_ring`.

    Uses a small buffer around the boundary to absorb floating-point gaps
    produced by Shapely's split() and buffer() operations.

    Args:
        segment:       room polygon edge
        boundary_ring: LinearRing / LineString of the inner plot perimeter
    """
    try:
        buffered = boundary_ring.buffer(BOUNDARY_BUFFER)
        overlap  = segment.intersection(buffered)
        linear   = _extract_linear_parts(overlap)
        if not linear:
            return None
        merged = linemerge(linear) if len(linear) > 1 else linear[0]
        if merged.is_empty or merged.length < MIN_WALL_LENGTH:
            return None
        # linemerge can return a MultiLineString if pieces aren't contiguous
        if isinstance(merged, MultiLineString):
            # Return the longest piece
            merged = max(merged.geoms, key=lambda g: g.length)
        return merged if isinstance(merged, LineString) else None
    except Exception as exc:
        logger.debug("Boundary test failed: %s", exc)
        return None


# ─────────────────────────────────────────────
# SHARED EDGE DETECTION (INTERIOR WALLS)
# ─────────────────────────────────────────────

def _find_shared_edges(polygons: List[Polygon]) -> List[LineString]:
    """
    Find all boundary segments shared between any two room polygons.

    For every pair (i, j): compute poly_i.boundary ∩ poly_j.boundary
    and extract the linear parts.
    """
    shared: List[LineString] = []

    for (i, poly_a), (j, poly_b) in combinations(enumerate(polygons), 2):
        # Quick spatial reject
        if not poly_a.intersects(poly_b):
            continue
        try:
            inters = poly_a.boundary.intersection(poly_b.boundary)
            for part in _extract_linear_parts(inters):
                if part.length >= MIN_WALL_LENGTH:
                    shared.append(part)
        except Exception as exc:
            logger.debug("Shared edge failed for (%d,%d): %s", i, j, exc)

    return shared


# ─────────────────────────────────────────────
# DEDUPLICATION
# ─────────────────────────────────────────────

def _deduplicate_segments(segments: List[dict]) -> List[dict]:
    """
    Remove duplicate segments. Exterior type wins over interior on same edge.
    """
    seen: Dict[Tuple, dict] = {}
    for seg in segments:
        line = LineString([
            (seg["start"]["x"], seg["start"]["y"]),
            (seg["end"]["x"],   seg["end"]["y"]),
        ])
        key = _normalise_endpoints(line)
        if key not in seen:
            seen[key] = seg
        else:
            if seg["type"] == "exterior" and seen[key]["type"] == "interior":
                seen[key] = seg
    return list(seen.values())


# ─────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────

def extract_wall_segments(
    room_polygons: List[Polygon],
    plot_polygon:  Polygon,
    inner_polygon: Optional[Polygon] = None,
) -> List[dict]:
    """
    Extract a unified, classified wall graph from room polygons.

    Args:
        room_polygons:  list of Shapely Polygons (room boundaries after BSP)
        plot_polygon:   original plot polygon (before setback) — kept for
                        reference / output context
        inner_polygon:  setback-applied polygon whose boundary defines the
                        exterior wall perimeter. If None, falls back to
                        plot_polygon.

    Returns:
        list of wall segment dicts with 'start', 'end', 'type', 'thickness',
        'length'.
    """
    all_segments: List[dict] = []

    # Use inner_polygon boundary for exterior wall detection.
    # Rooms are carved from inner_polygon — their outer faces lie on its
    # boundary, NOT the original plot boundary.
    reference_polygon = inner_polygon if inner_polygon is not None else plot_polygon
    boundary_ring     = reference_polygon.boundary  # LinearRing

    # ── Step 1: Classify every edge of every room polygon ───────────────────
    for poly in room_polygons:
        for edge in _coords_to_edges(poly):
            overlap = _segment_on_boundary(edge, boundary_ring)
            if overlap is not None:
                all_segments.append(
                    _line_to_dict(overlap, "exterior", EXTERIOR_WALL_THICKNESS)
                )
            else:
                all_segments.append(
                    _line_to_dict(edge, "interior", INTERIOR_WALL_THICKNESS)
                )

    # ── Step 2: Find all shared edges between rooms (definitive interior walls)
    interior_shared = _find_shared_edges(room_polygons)
    shared_keys     = {_normalise_endpoints(s) for s in interior_shared}

    # ── Step 3: Re-classify provisional segments that are actually shared ────
    for seg in all_segments:
        line = LineString([
            (seg["start"]["x"], seg["start"]["y"]),
            (seg["end"]["x"],   seg["end"]["y"]),
        ])
        key = _normalise_endpoints(line)
        # Shared edge → interior (never override a confirmed exterior)
        if key in shared_keys and seg["type"] != "exterior":
            seg["type"]      = "interior"
            seg["thickness"] = INTERIOR_WALL_THICKNESS

    # ── Step 4: Add any shared edges not already captured ───────────────────
    existing_keys = {
        _normalise_endpoints(LineString([
            (s["start"]["x"], s["start"]["y"]),
            (s["end"]["x"],   s["end"]["y"]),
        ]))
        for s in all_segments
    }
    for seg_line in interior_shared:
        key = _normalise_endpoints(seg_line)
        if key not in existing_keys:
            all_segments.append(
                _line_to_dict(seg_line, "interior", INTERIOR_WALL_THICKNESS)
            )
            existing_keys.add(key)

    # ── Step 5: Deduplicate ──────────────────────────────────────────────────
    result = _deduplicate_segments(all_segments)

    # ── Step 6: Length filter ────────────────────────────────────────────────
    result = [s for s in result if s["length"] >= MIN_WALL_LENGTH]

    n_ext = sum(1 for s in result if s["type"] == "exterior")
    n_int = sum(1 for s in result if s["type"] == "interior")
    logger.info(
        "Wall extraction: %d raw → %d unique (%d exterior, %d interior)",
        len(all_segments), len(result), n_ext, n_int,
    )

    return result
