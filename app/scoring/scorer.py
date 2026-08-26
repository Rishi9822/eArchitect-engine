"""
Redesigned Layout Scoring Engine.

Produces a normalized 0–1 quality score based on multiple
architectural metrics:

1.  Buildable Utilization   — room area / buildable area
2.  Building Coverage       — built-up area / plot area
3.  Aspect Quality          — room-type-aware shape quality
4.  Adjacency               — room-level adjacency correctness
5.  Circulation             — graph-based reachability
6.  Natural Light           — exterior wall + window for light-needing rooms
7.  Ventilation             — airflow accessibility
8.  Parking Accessibility   — dimensional + road access
9.  Dead Space Efficiency   — weighted dead space penalty
10. Constraint Compliance   — hard/soft constraint adherence

Score = weighted average of all metrics.
"""
from __future__ import annotations

import logging
from typing import List, Dict, Optional

from shapely.geometry import Polygon

from ..config import SCORE_WEIGHTS, SQ_M_TO_SQ_FT, get_room_defaults
from ..geometry.polygon_utils import aspect_ratio
from .adjacency import score_adjacency
from .metrics import (
    score_natural_light,
    score_ventilation,
    score_dead_space,
    score_parking_accessibility,
    score_constraint_compliance,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# INDIVIDUAL METRICS
# ─────────────────────────────────────────────

def _score_buildable_utilization(
    room_polygons: List[Polygon],
    inner_polygon: Polygon,
) -> float:
    """room_area / buildable_area, clamped to [0, 1]."""
    if inner_polygon.area <= 0:
        return 0.0
    total = sum(p.area for p in room_polygons)
    return min(1.0, total / inner_polygon.area)


def _score_building_coverage(
    room_polygons: List[Polygon],
    plot_polygon: Polygon,
) -> float:
    """built-up area / original plot area."""
    if plot_polygon.area <= 0:
        return 0.0
    total = sum(p.area for p in room_polygons)
    coverage = total / plot_polygon.area
    # Ideal coverage is 40-70%; penalise extremes
    if 0.35 <= coverage <= 0.75:
        return 1.0
    elif coverage < 0.35:
        return max(0.3, coverage / 0.35)
    else:
        return max(0.5, 1.0 - (coverage - 0.75) / 0.25)


def _aspect_ratio_score_for_type(poly: Polygon, room_type: str) -> float:
    """
    Room-type-aware aspect ratio scoring.

    Uses the preferred ratio from config rather than assuming
    square = best for all rooms.
    """
    ar = aspect_ratio(poly)
    defaults = get_room_defaults(room_type)
    preferred = defaults.preferred_aspect_ratio
    max_ar = defaults.max_aspect_ratio

    if ar <= preferred:
        return 1.0
    elif ar <= max_ar:
        # Linear decay from 1.0 to 0.3 between preferred and max
        return max(0.3, 1.0 - 0.7 * (ar - preferred) / (max_ar - preferred))
    else:
        # Below 0.3 for exceeding max
        return max(0.0, 0.3 - 0.1 * (ar - max_ar))


def _score_aspect_quality(
    room_polygons: Dict[str, Polygon],
    room_types: Dict[str, str],
) -> float:
    """Average room-type-aware aspect ratio quality."""
    if not room_polygons:
        return 0.0

    scores = []
    for room_id, poly in room_polygons.items():
        rtype = room_types.get(room_id, "")
        scores.append(_aspect_ratio_score_for_type(poly, rtype))

    return sum(scores) / len(scores)


# ─────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────

def score_layout(
    room_polygons_dict: Dict[str, Polygon],
    room_types: Dict[str, str],
    room_polygons_list: List[Polygon],
    plot_polygon: Polygon,
    inner_polygon: Polygon,
    zone_polygons: Dict[str, Polygon],
    windows: List[dict],
    dead_spaces: List[dict],
    parking_entities: List[dict],
    circulation_data: dict,
    validation_warnings: List[dict],
    validation_errors: List[dict],
) -> dict:
    """
    Compute comprehensive quality scores for a generated layout.

    Returns:
        dict with individual metric scores and weighted overall score.
    """
    # Individual metrics
    util = _score_buildable_utilization(room_polygons_list, inner_polygon)
    coverage = _score_building_coverage(room_polygons_list, plot_polygon)
    aspect = _score_aspect_quality(room_polygons_dict, room_types)
    adj = score_adjacency(room_polygons_dict, room_types, zone_polygons)
    circ = circulation_data.get("score", 0.5)
    light = score_natural_light(room_polygons_dict, room_types, inner_polygon, windows)
    vent = score_ventilation(room_polygons_dict, room_types, inner_polygon, windows)
    park = score_parking_accessibility(parking_entities)
    dead = score_dead_space(dead_spaces, inner_polygon)
    compliance = score_constraint_compliance(
        validation_warnings, validation_errors, len(room_polygons_dict)
    )

    # Weighted overall score
    weights = SCORE_WEIGHTS
    overall = (
        weights["buildable_utilization"] * util +
        weights["building_coverage"] * coverage +
        weights["aspect_quality"] * aspect +
        weights["adjacency"] * adj +
        weights["circulation"] * circ +
        weights["natural_light"] * light +
        weights["ventilation"] * vent +
        weights["parking_accessibility"] * park +
        weights["dead_space_efficiency"] * dead +
        weights["constraint_compliance"] * compliance
    )
    overall = round(min(1.0, max(0.0, overall)), 4)

    breakdown = {
        "buildable_utilization": round(util, 4),
        "building_coverage": round(coverage, 4),
        "aspect_quality": round(aspect, 4),
        "adjacency": round(adj, 4),
        "circulation": round(circ, 4),
        "natural_light": round(light, 4),
        "ventilation": round(vent, 4),
        "parking_accessibility": round(park, 4),
        "dead_space_efficiency": round(dead, 4),
        "constraint_compliance": round(compliance, 4),
        "overall": overall,
    }

    logger.info(
        "Layout score: util=%.3f cov=%.3f asp=%.3f adj=%.3f circ=%.3f "
        "light=%.3f vent=%.3f park=%.3f dead=%.3f comp=%.3f → overall=%.3f",
        util, coverage, aspect, adj, circ, light, vent, park, dead,
        compliance, overall,
    )
    return breakdown
