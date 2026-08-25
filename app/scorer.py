"""
Layout Scoring Engine.

Produces a normalized 0–1 quality score for a generated floor plan based
on four geometric metrics:

  1. Space Utilization     — what fraction of inner plot area is assigned to rooms
  2. Aspect Ratio Quality  — average room shape quality (square = best)
  3. Adjacency Correctness — are the right zones placed near each other?
  4. Circulation Efficiency— can all rooms be reached via reasonable paths?

Score = weighted average of all four metrics.
"""
from __future__ import annotations

import math
import logging
from typing import List, Dict, Tuple, Optional

import numpy as np
from shapely.geometry import Polygon

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# SCORING WEIGHTS
# ─────────────────────────────────────────────

WEIGHT_UTILIZATION  = 0.35
WEIGHT_ASPECT       = 0.25
WEIGHT_ADJACENCY    = 0.25
WEIGHT_CIRCULATION  = 0.15

# ─────────────────────────────────────────────
# ADJACENCY PREFERENCE TABLE
#
# Desired adjacent zone pairs (undirected).
# Each pair earns +1 point if satisfied.
# ─────────────────────────────────────────────

PREFERRED_ADJACENCY: List[Tuple[str, str]] = [
    ("public",  "service"),   # living near kitchen
    ("public",  "private"),   # living near bedrooms (for access)
    ("private", "service"),   # bedrooms near bathrooms
]

# Room types that should be near an exterior boundary (for light/ventilation)
VENTILATION_ROOMS = {"bedroom", "living", "dining"}


# ─────────────────────────────────────────────
# METRIC 1: SPACE UTILIZATION
# ─────────────────────────────────────────────

def _score_utilization(
    room_polygons: List[Polygon],
    inner_polygon: Polygon,
) -> float:
    """
    Score = used_area / inner_plot_area, clamped to [0, 1].

    A score of 1.0 means 100% of the available (post-setback) plot is used.
    """
    if inner_polygon.area <= 0:
        return 0.0
    total_room_area = sum(p.area for p in room_polygons)
    ratio = total_room_area / inner_polygon.area
    return min(1.0, ratio)


# ─────────────────────────────────────────────
# METRIC 2: ASPECT RATIO QUALITY
# ─────────────────────────────────────────────

def _aspect_ratio_score(poly: Polygon) -> float:
    """
    Score a single room's shape:
      - Perfect square → 1.0
      - 2:1 ratio      → ~0.75
      - 4:1 ratio      → ~0.25 (maximum tolerated)
      - > 4:1          → 0.0

    Uses minimum rotated bounding-box for more accuracy than axis-aligned bounds.
    """
    try:
        minx, miny, maxx, maxy = poly.minimum_rotated_rectangle.bounds
    except Exception:
        minx, miny, maxx, maxy = poly.bounds

    w = maxx - minx
    h = maxy - miny
    if min(w, h) <= 0:
        return 0.0

    ratio = max(w, h) / min(w, h)  # always ≥ 1
    # Linearly decay from 1.0 (ratio=1) to 0.0 (ratio=4)
    score = max(0.0, 1.0 - (ratio - 1.0) / 3.0)
    return score


def _score_aspect_ratio(room_polygons: List[Polygon]) -> float:
    """Average aspect ratio quality across all rooms."""
    if not room_polygons:
        return 0.0
    scores = [_aspect_ratio_score(p) for p in room_polygons]
    return float(np.mean(scores))


# ─────────────────────────────────────────────
# METRIC 3: ADJACENCY CORRECTNESS
# ─────────────────────────────────────────────

def _polygons_touch(a: Polygon, b: Polygon) -> bool:
    """True if two polygons share a boundary (touch or intersect boundary)."""
    try:
        return a.touches(b) or (a.intersects(b) and not a.intersection(b).is_empty)
    except Exception:
        return False


def _score_adjacency(
    zone_polygons: Dict[str, Polygon],
) -> float:
    """
    For each preferred (zone_a, zone_b) pair, check if the two zone
    polygons are adjacent (touch or overlap boundary).

    Score = satisfied_pairs / total_preferred_pairs
    """
    if not zone_polygons or len(zone_polygons) < 2:
        return 1.0  # Can't evaluate → neutral

    satisfied = 0
    total = len(PREFERRED_ADJACENCY)

    for zone_a, zone_b in PREFERRED_ADJACENCY:
        poly_a = zone_polygons.get(zone_a)
        poly_b = zone_polygons.get(zone_b)
        if poly_a is None or poly_b is None:
            # Zone doesn't exist in this plan → not penalised
            total -= 1
            continue
        if _polygons_touch(poly_a, poly_b):
            satisfied += 1

    if total <= 0:
        return 1.0
    return satisfied / total


# ─────────────────────────────────────────────
# METRIC 4: CIRCULATION EFFICIENCY
# ─────────────────────────────────────────────

def _centroid_distance(a: Polygon, b: Polygon) -> float:
    """Euclidean distance between polygon centroids."""
    ca = a.centroid
    cb = b.centroid
    return math.sqrt((ca.x - cb.x) ** 2 + (ca.y - cb.y) ** 2)


def _score_circulation(
    zone_polygons: Dict[str, Polygon],
    inner_polygon: Polygon,
) -> float:
    """
    Measures how compactly the zones are arranged relative to plot size.

    Lower total inter-zone centroid distance → better circulation.

    1. Compute sum of centroid distances between all zone pairs.
    2. Normalise by the plot's effective diameter.
    3. Score = 1 - normalized_distance (clamped to [0, 1]).
    """
    zones = list(zone_polygons.values())
    if len(zones) < 2:
        return 1.0

    # Effective plot diameter from area
    plot_diameter = math.sqrt(inner_polygon.area / math.pi) * 2.0
    if plot_diameter <= 0:
        return 1.0

    total_distance = 0.0
    n_pairs = 0
    for i in range(len(zones)):
        for j in range(i + 1, len(zones)):
            total_distance += _centroid_distance(zones[i], zones[j])
            n_pairs += 1

    if n_pairs == 0:
        return 1.0

    avg_distance = total_distance / n_pairs
    normalised = avg_distance / plot_diameter
    score = max(0.0, 1.0 - normalised)
    return score


# ─────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────

def score_layout(
    room_polygons: List[Polygon],
    inner_polygon: Polygon,
    zone_polygons: Dict[str, Polygon],
) -> dict:
    """
    Compute a structured quality score for a generated layout.

    Args:
        room_polygons: list of individual room Shapely Polygons
        inner_polygon: setback-applied plot polygon
        zone_polygons: dict of zone_name → zone Polygon

    Returns:
        {
            "space_utilization":    float,   # 0–1
            "aspect_ratio_quality": float,   # 0–1
            "adjacency_correctness":float,   # 0–1
            "circulation_efficiency":float,  # 0–1
            "overall":              float,   # 0–1 weighted average
        }
    """
    util  = _score_utilization(room_polygons, inner_polygon)
    asp   = _score_aspect_ratio(room_polygons)
    adj   = _score_adjacency(zone_polygons)
    circ  = _score_circulation(zone_polygons, inner_polygon)

    overall = (
        WEIGHT_UTILIZATION  * util +
        WEIGHT_ASPECT       * asp  +
        WEIGHT_ADJACENCY    * adj  +
        WEIGHT_CIRCULATION  * circ
    )
    overall = round(min(1.0, max(0.0, overall)), 4)

    breakdown = {
        "space_utilization":     round(util, 4),
        "aspect_ratio_quality":  round(asp,  4),
        "adjacency_correctness": round(adj,  4),
        "circulation_efficiency":round(circ, 4),
        "overall":               overall,
    }

    logger.info(
        "Layout score: util=%.3f asp=%.3f adj=%.3f circ=%.3f → overall=%.3f",
        util, asp, adj, circ, overall,
    )
    return breakdown
