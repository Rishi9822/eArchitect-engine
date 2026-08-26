"""
Room-level adjacency scoring.

Evaluates room adjacency based on configurable preferred/avoid
rules, with zone-level fallback.
"""
from __future__ import annotations

import logging
from typing import List, Dict, Set, Tuple

from shapely.geometry import Polygon

from ..config import (
    ADJACENCY_RULES,
    PREFERRED_ZONE_ADJACENCY,
    ZONE_MAP,
)
from ..geometry.polygon_utils import polygons_share_boundary

logger = logging.getLogger(__name__)


def compute_room_adjacency(
    room_polygons: Dict[str, Polygon],
    room_types: Dict[str, str],
) -> Dict[str, Set[str]]:
    """
    Build room adjacency map from geometric proximity.

    Returns:
        {room_id: set of adjacent room_ids}
    """
    adjacency: Dict[str, Set[str]] = {rid: set() for rid in room_polygons}
    room_ids = list(room_polygons.keys())

    for i in range(len(room_ids)):
        for j in range(i + 1, len(room_ids)):
            id_a, id_b = room_ids[i], room_ids[j]
            if polygons_share_boundary(
                room_polygons[id_a], room_polygons[id_b],
                min_length=0.1,
            ):
                adjacency[id_a].add(id_b)
                adjacency[id_b].add(id_a)

    return adjacency


def score_adjacency(
    room_polygons: Dict[str, Polygon],
    room_types: Dict[str, str],
    zone_polygons: Dict[str, Polygon],
) -> float:
    """
    Score room-level adjacency quality.

    Evaluates:
    1. Room-level preferred adjacencies (from ADJACENCY_RULES)
    2. Room-level avoid adjacencies
    3. Zone-level fallback

    Returns:
        Score 0.0 to 1.0
    """
    adjacency = compute_room_adjacency(room_polygons, room_types)

    satisfied = 0
    total_checks = 0
    penalty = 0

    # ── Room-level preferred adjacency ────────────────────────────
    for room_id, neighbors in adjacency.items():
        rtype = room_types.get(room_id, "").lower()
        rules = ADJACENCY_RULES.get(rtype)
        if not rules:
            continue

        neighbor_types = {room_types.get(n, "").lower() for n in neighbors}

        # Check preferred
        for pref in rules.preferred:
            total_checks += 1
            if pref in neighbor_types:
                satisfied += 1

        # Check avoid
        for avoid in rules.avoid:
            if avoid in neighbor_types:
                penalty += 1

    # ── Zone-level fallback ───────────────────────────────────────
    if total_checks == 0:
        # No room-level rules applied — use zone adjacency
        zone_satisfied = 0
        zone_total = 0

        for zone_a, zone_b in PREFERRED_ZONE_ADJACENCY:
            poly_a = zone_polygons.get(zone_a)
            poly_b = zone_polygons.get(zone_b)
            if poly_a is None or poly_b is None:
                continue
            zone_total += 1
            try:
                if poly_a.touches(poly_b) or (
                    poly_a.intersects(poly_b) and
                    not poly_a.intersection(poly_b).is_empty
                ):
                    zone_satisfied += 1
            except Exception:
                pass

        if zone_total > 0:
            return zone_satisfied / zone_total
        return 1.0

    # ── Combine ───────────────────────────────────────────────────
    base_score = satisfied / total_checks if total_checks > 0 else 1.0
    penalty_score = min(0.3, penalty * 0.05)

    return max(0.0, base_score - penalty_score)
