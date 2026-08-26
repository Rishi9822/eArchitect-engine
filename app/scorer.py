"""
Backward-compatibility bridge for scorer.
Re-exports from app.scoring.scorer.
"""
from typing import List, Dict
from shapely.geometry import Polygon
from .scoring.scorer import (
    score_layout as _score_layout,
    _score_buildable_utilization,
    _score_aspect_quality,
)
from .scoring.adjacency import score_adjacency


def score_layout(
    room_polygons: List[Polygon],
    inner_polygon: Polygon,
    zone_polygons: Dict[str, Polygon],
) -> dict:
    """Legacy score_layout signature."""
    room_dict = {f"room_{i}": p for i, p in enumerate(room_polygons)}
    room_types = {f"room_{i}": "living" for i in range(len(room_polygons))}

    util = _score_buildable_utilization(room_polygons, inner_polygon)
    asp = _score_aspect_quality(room_dict, room_types)
    adj = score_adjacency(room_dict, room_types, zone_polygons)
    circ = 0.8  # fallback

    overall = round(0.35 * util + 0.25 * asp + 0.25 * adj + 0.15 * circ, 4)

    return {
        "space_utilization": round(util, 4),
        "aspect_ratio_quality": round(asp, 4),
        "adjacency_correctness": round(adj, 4),
        "circulation_efficiency": round(circ, 4),
        "overall": overall,
    }
