"""
Polygon normalization utilities.

Ensures consistent polygon orientation, coordinate snapping,
and degenerate point removal.
"""
from __future__ import annotations

import logging
from typing import List, Tuple

from shapely.geometry import Polygon, MultiPolygon
from shapely.validation import make_valid

from ..config import MIN_POLYGON_AREA_SQM, COORDINATE_SNAP

logger = logging.getLogger(__name__)


def ensure_valid(poly: Polygon) -> Polygon:
    """
    Return a valid, non-degenerate Shapely Polygon.

    If make_valid produces a MultiPolygon, returns the largest piece.
    """
    if not poly.is_valid:
        poly = make_valid(poly)
    if poly.is_empty or poly.area < 1e-6:
        raise ValueError("Degenerate polygon after validation")
    if isinstance(poly, MultiPolygon):
        poly = max(poly.geoms, key=lambda g: g.area)
    if not isinstance(poly, Polygon):
        raise ValueError(f"Expected Polygon, got {type(poly).__name__}")
    return poly


def normalize_polygon(
    points: List[Tuple[float, float]],
    force_ccw: bool = True,
) -> Polygon:
    """
    Build a Shapely Polygon from raw points and normalize it.

    Steps:
    1. Create polygon
    2. Make valid if needed
    3. Force CCW orientation if requested
    4. Snap coordinates to grid
    """
    poly = Polygon(points)
    poly = ensure_valid(poly)

    # Force counter-clockwise orientation
    if force_ccw and not poly.exterior.is_ccw:
        poly = Polygon(list(reversed(list(poly.exterior.coords))))

    return poly


def snap_polygon(poly: Polygon, tolerance: float = COORDINATE_SNAP) -> Polygon:
    """
    Snap all polygon coordinates to a grid defined by tolerance.

    This reduces floating-point noise from Shapely operations.
    """
    def snap(v: float) -> float:
        return round(v / tolerance) * tolerance

    coords = [(snap(x), snap(y)) for x, y in poly.exterior.coords]
    result = Polygon(coords)
    if not result.is_valid:
        return poly  # keep original if snapping broke validity
    return result


def poly_to_coord_list(poly: Polygon, precision: int = 4) -> List[dict]:
    """Convert polygon exterior ring to list of {x, y} dicts, excluding closing point."""
    return [
        {"x": round(x, precision), "y": round(y, precision)}
        for x, y in list(poly.exterior.coords)[:-1]
    ]
