"""
Candidate diversity analysis and selection.

Ensures that the returned candidate set contains genuinely
different layouts rather than near-duplicates.

Strategy: quality first, diversity second.

Pipeline:
  1. Remove exact duplicates (via fingerprint)
  2. Compute pairwise diversity scores
  3. Greedy farthest-point selection to pick diverse set
  4. Never let diversity override quality ranking
"""
from __future__ import annotations

import math
import logging
from typing import List, Dict, Tuple

from .fingerprint import deduplicate_candidates

logger = logging.getLogger(__name__)


def _centroid_distance(rooms_a: List[dict], rooms_b: List[dict]) -> float:
    """
    Compute average centroid displacement between two candidate layouts.

    Matches rooms by type+id. Returns average Euclidean distance in metres.
    """
    map_a = {r["id"]: r for r in rooms_a}
    map_b = {r["id"]: r for r in rooms_b}

    common = set(map_a.keys()) & set(map_b.keys())
    if not common:
        return 10.0  # Completely different room sets → maximally diverse

    total_dist = 0.0
    for rid in common:
        ca = map_a[rid].get("centroid", {})
        cb = map_b[rid].get("centroid", {})
        dx = ca.get("x", 0) - cb.get("x", 0)
        dy = ca.get("y", 0) - cb.get("y", 0)
        total_dist += math.sqrt(dx * dx + dy * dy)

    return total_dist / len(common)


def _area_difference(rooms_a: List[dict], rooms_b: List[dict]) -> float:
    """
    Compute average area difference between two candidates.

    Returns average absolute area difference in sqm.
    """
    map_a = {r["id"]: r for r in rooms_a}
    map_b = {r["id"]: r for r in rooms_b}

    common = set(map_a.keys()) & set(map_b.keys())
    if not common:
        return 5.0

    total_diff = 0.0
    for rid in common:
        a_area = map_a[rid].get("area_sqm", 0)
        b_area = map_b[rid].get("area_sqm", 0)
        total_diff += abs(a_area - b_area)

    return total_diff / len(common)


def _strategy_bonus(c_a: dict, c_b: dict) -> float:
    """Small bonus for different strategies."""
    if c_a.get("strategy") != c_b.get("strategy"):
        return 0.5
    return 0.0


def pairwise_diversity(c_a: dict, c_b: dict) -> float:
    """
    Compute a diversity score between two candidates.

    Higher score = more different.

    Components:
    - centroid displacement (0-10m typical)
    - area difference (0-5 sqm typical)
    - strategy difference bonus

    Normalised to 0-1 range.
    """
    rooms_a = c_a.get("rooms", [])
    rooms_b = c_b.get("rooms", [])

    cd = _centroid_distance(rooms_a, rooms_b)
    ad = _area_difference(rooms_a, rooms_b)
    sb = _strategy_bonus(c_a, c_b)

    # Corridor presence difference
    corr_a = len(c_a.get("corridors", []))
    corr_b = len(c_b.get("corridors", []))
    corr_diff = 1.0 if corr_a != corr_b else 0.0

    # Normalize: cd typically 0-10m, ad typically 0-10sqm
    cd_norm = min(1.0, cd / 5.0)
    ad_norm = min(1.0, ad / 3.0)

    diversity = (
        0.45 * cd_norm +
        0.20 * ad_norm +
        0.15 * sb +
        0.20 * corr_diff
    )
    return min(1.0, diversity)


def select_diverse_candidates(
    candidates: List[dict],
    target_count: int = 5,
    min_diversity: float = 0.05,
) -> List[dict]:
    """
    Select a diverse subset of candidates using greedy farthest-point.

    Quality is preserved: candidates are assumed to be pre-sorted by quality.
    The algorithm selects the best candidate first, then iteratively
    picks the candidate that is most different from the already-selected set.

    Args:
        candidates:    quality-sorted candidates (best first)
        target_count:  number to select
        min_diversity: minimum diversity threshold to add a candidate

    Returns:
        list of selected candidates
    """
    if len(candidates) <= target_count:
        return candidates

    # De-duplicate first
    unique = deduplicate_candidates(candidates)
    if len(unique) <= target_count:
        return unique

    # Start with the best candidate
    selected = [unique[0]]
    remaining = list(unique[1:])

    while len(selected) < target_count and remaining:
        best_idx = -1
        best_min_div = -1.0

        for i, cand in enumerate(remaining):
            # Minimum diversity to any already-selected candidate
            min_div = min(
                pairwise_diversity(cand, sel) for sel in selected
            )
            if min_div > best_min_div:
                best_min_div = min_div
                best_idx = i

        if best_idx < 0 or best_min_div < min_diversity:
            # Remaining candidates are too similar; fill from quality order
            for cand in remaining:
                if len(selected) >= target_count:
                    break
                selected.append(cand)
            break

        selected.append(remaining.pop(best_idx))

    return selected
