"""
Layout fingerprinting — detect geometrically identical candidates.

Normalises room geometry and produces a deterministic hash so that
two candidates with identical room polygons are recognised as
duplicates even if their strategy labels differ.
"""
from __future__ import annotations

import hashlib
import logging
from typing import List, Dict, Tuple

logger = logging.getLogger(__name__)

# Quantisation grid (metres) — coordinates are rounded to this
# resolution before hashing to absorb floating-point noise.
_QUANT = 0.1


def _quantize(v: float) -> float:
    """Round to _QUANT grid."""
    return round(v / _QUANT) * _QUANT


def layout_fingerprint(rooms: List[dict]) -> str:
    """
    Compute a deterministic fingerprint string for a candidate's rooms.

    The fingerprint captures:
      - room type
      - quantised centroid (x, y)
      - quantised area

    Rooms are sorted by type then centroid so ordering doesn't matter.

    Args:
        rooms: list of room dicts with 'type', 'centroid', 'area_sqm'

    Returns:
        hex digest string
    """
    components: List[Tuple] = []
    for r in rooms:
        rtype = r.get("type", "")
        cx = _quantize(r.get("centroid", {}).get("x", 0.0))
        cy = _quantize(r.get("centroid", {}).get("y", 0.0))
        area = round(r.get("area_sqm", 0.0), 1)
        components.append((rtype, cx, cy, area))

    # Sort for order-independence
    components.sort()

    raw = str(components).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def deduplicate_candidates(candidates: List[dict]) -> List[dict]:
    """
    Remove geometrically duplicate candidates.

    Two candidates are duplicates if they have the same layout
    fingerprint (identical room types, centroids, and areas).

    Keeps the first occurrence (highest quality / earliest generated).

    Args:
        candidates: list of processed candidate dicts

    Returns:
        de-duplicated list
    """
    seen: Dict[str, int] = {}
    unique: List[dict] = []

    for c in candidates:
        rooms = c.get("rooms", [])
        fp = layout_fingerprint(rooms)
        c["_fingerprint"] = fp

        if fp not in seen:
            seen[fp] = len(unique)
            unique.append(c)
        else:
            logger.info(
                "Duplicate candidate removed: %s (fingerprint=%s, matches %s)",
                c.get("id", "?"), fp, unique[seen[fp]].get("id", "?"),
            )

    return unique
