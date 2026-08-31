"""
Layout fingerprinting and geometric deduplication.

Detects and eliminates geometrically identical or near-duplicate candidates
based on room centroids, areas, and corridor positions.
"""
from __future__ import annotations

import math
import hashlib
import logging
from typing import List, Dict, Tuple, Optional

from ..config import (
    DEDUP_CENTROID_TOLERANCE_M,
    DEDUP_AREA_TOLERANCE_SQM,
)

logger = logging.getLogger(__name__)

# Quantisation grid (metres) for fingerprint hashing
_QUANT = 0.1


def _quantize(v: float) -> float:
    """Round to _QUANT grid."""
    return round(v / _QUANT) * _QUANT


def layout_fingerprint(rooms: List[dict], corridors: Optional[List[dict]] = None) -> str:
    """
    Compute a deterministic fingerprint string for a candidate's rooms and corridors.
    """
    components: List[Tuple] = []
    for r in rooms:
        rtype = r.get("type", "")
        cx = _quantize(r.get("centroid", {}).get("x", 0.0))
        cy = _quantize(r.get("centroid", {}).get("y", 0.0))
        area = round(r.get("area_sqm", 0.0), 1)
        components.append((rtype, cx, cy, area))

    if corridors:
        for c in corridors:
            cx = _quantize(c.get("centroid", {}).get("x", 0.0) if c.get("centroid") else 0.0)
            cy = _quantize(c.get("centroid", {}).get("y", 0.0) if c.get("centroid") else 0.0)
            area = round(c.get("area_sqm", 0.0), 1)
            components.append(("corridor", cx, cy, area))

    components.sort()
    raw = str(components).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def are_candidates_geometrically_identical(
    cand_a: dict,
    cand_b: dict,
    centroid_tol: float = DEDUP_CENTROID_TOLERANCE_M,
    area_tol: float = DEDUP_AREA_TOLERANCE_SQM,
) -> bool:
    """
    Check whether two candidates have effectively identical room & corridor geometry.
    """
    rooms_a = cand_a.get("rooms", [])
    rooms_b = cand_b.get("rooms", [])
    if len(rooms_a) != len(rooms_b):
        return False

    map_a = {r["id"]: r for r in rooms_a}
    map_b = {r["id"]: r for r in rooms_b}

    if set(map_a.keys()) != set(map_b.keys()):
        return False

    for rid, r_a in map_a.items():
        r_b = map_b[rid]
        ca = r_a.get("centroid", {}) or {}
        cb = r_b.get("centroid", {}) or {}
        dx = ca.get("x", 0.0) - cb.get("x", 0.0)
        dy = ca.get("y", 0.0) - cb.get("y", 0.0)
        dist = math.hypot(dx, dy)
        if dist > centroid_tol:
            return False

        area_diff = abs(r_a.get("area_sqm", 0.0) - r_b.get("area_sqm", 0.0))
        if area_diff > area_tol:
            return False

    # Check corridors if any
    corrs_a = cand_a.get("corridors", [])
    corrs_b = cand_b.get("corridors", [])
    if len(corrs_a) != len(corrs_b):
        return False
    if corrs_a and corrs_b:
        ca = corrs_a[0].get("centroid") or {}
        cb = corrs_b[0].get("centroid") or {}
        dist = math.hypot(ca.get("x", 0.0) - cb.get("x", 0.0), ca.get("y", 0.0) - cb.get("y", 0.0))
        if dist > centroid_tol:
            return False

    return True


def deduplicate_candidates(
    candidates: List[dict],
    centroid_tol: float = DEDUP_CENTROID_TOLERANCE_M,
    area_tol: float = DEDUP_AREA_TOLERANCE_SQM,
) -> List[dict]:
    """
    Remove geometrically duplicate candidates.

    Assumes candidates are pre-sorted by quality/validity.
    Keeps the higher-ranked candidate and drops any subsequent geometric duplicates.
    """
    unique: List[dict] = []

    for c in candidates:
        rooms = c.get("rooms", [])
        corrs = c.get("corridors", [])
        c["_fingerprint"] = layout_fingerprint(rooms, corrs)

        is_dup = False
        for u in unique:
            if are_candidates_geometrically_identical(c, u, centroid_tol, area_tol):
                is_dup = True
                logger.info(
                    "Duplicate candidate dropped: %s (strategy=%s, var=%s) matches %s (strategy=%s, var=%s)",
                    c.get("id", "?"), c.get("strategy", "?"), c.get("variation", "?"),
                    u.get("id", "?"), u.get("strategy", "?"), u.get("variation", "?"),
                )
                break

        if not is_dup:
            unique.append(c)

    return unique
