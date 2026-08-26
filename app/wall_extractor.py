"""
Backward-compatibility bridge for wall_extractor.
Re-exports from app.walls.extractor.
"""
from typing import List, Optional
from shapely.geometry import Polygon
from .walls.extractor import extract_wall_segments as _extract_wall_segments


def extract_wall_segments(
    room_polygons: List[Polygon],
    plot_polygon: Polygon,
    inner_polygon: Optional[Polygon] = None,
) -> List[dict]:
    """Legacy extract_wall_segments signature."""
    room_ids = [f"room_{i}" for i in range(len(room_polygons))]
    return _extract_wall_segments(room_polygons, room_ids, plot_polygon, inner_polygon)
