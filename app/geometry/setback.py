"""
Setback processing.

Applies building setback lines by computing an inward buffer
on the plot polygon.  Handles edge cases: collapsed polygons,
multi-polygon results, and invalid geometry.
"""
from __future__ import annotations

import logging
from typing import Optional

from shapely.geometry import Polygon, MultiPolygon
from shapely.validation import make_valid

from ..config import MIN_POLYGON_AREA_SQM
from .normalization import ensure_valid

logger = logging.getLogger(__name__)


class SetbackError(Exception):
    """Raised when setback produces no usable buildable area."""
    def __init__(self, message: str, code: str = "NO_BUILDABLE_AREA"):
        self.code = code
        super().__init__(message)


def apply_setback(
    polygon: Polygon,
    distance: float,
    min_area_sqm: float = MIN_POLYGON_AREA_SQM,
) -> Polygon:
    """
    Apply building setback by inward buffer (negative offset).

    Args:
        polygon:      original plot polygon
        distance:     setback distance in metres (≥ 0)
        min_area_sqm: minimum acceptable buildable area

    Returns:
        Polygon — the buildable area after setback

    Raises:
        SetbackError: if setback collapses or invalidates the plot
    """
    if distance < 0:
        raise SetbackError(
            f"Setback must be non-negative, got {distance}",
            code="INVALID_SETBACK",
        )

    if distance == 0:
        return polygon

    # mitre join style for clean corners on irregular polygons
    buffered = polygon.buffer(-distance, join_style=2, mitre_limit=5.0)

    # Handle empty result
    if buffered.is_empty:
        raise SetbackError(
            f"Setback of {distance}m completely eliminates the plot "
            f"(original area: {polygon.area:.2f} sqm)",
            code="NO_BUILDABLE_AREA",
        )

    # Handle multi-polygon result (can happen with deeply concave plots)
    if isinstance(buffered, MultiPolygon):
        pieces = sorted(buffered.geoms, key=lambda g: g.area, reverse=True)
        largest = pieces[0]
        if largest.area < min_area_sqm:
            raise SetbackError(
                f"Setback of {distance}m produces only tiny fragments "
                f"(largest: {largest.area:.2f} sqm)",
                code="NO_BUILDABLE_AREA",
            )
        logger.warning(
            "Setback produced %d polygon fragments; using largest (%.2f sqm)",
            len(pieces), largest.area,
        )
        buffered = largest

    # Validate result
    if not isinstance(buffered, Polygon):
        try:
            buffered = make_valid(buffered)
            if isinstance(buffered, MultiPolygon):
                buffered = max(buffered.geoms, key=lambda g: g.area)
        except Exception:
            pass

    if not isinstance(buffered, Polygon) or buffered.is_empty:
        raise SetbackError(
            f"Setback of {distance}m produced invalid geometry",
            code="NO_BUILDABLE_AREA",
        )

    if buffered.area < min_area_sqm:
        raise SetbackError(
            f"Setback of {distance}m leaves insufficient buildable area "
            f"({buffered.area:.2f} sqm < {min_area_sqm} sqm minimum)",
            code="NO_BUILDABLE_AREA",
        )

    return ensure_valid(buffered)


def validate_setback(
    plot_polygon: Polygon,
    setback: float,
) -> dict:
    """
    Validate setback feasibility without actually applying it.

    Returns:
        dict with 'feasible', 'original_area_sqm', 'estimated_buildable_sqm'
    """
    if setback <= 0:
        return {
            "feasible": True,
            "original_area_sqm": plot_polygon.area,
            "estimated_buildable_sqm": plot_polygon.area,
        }

    try:
        buildable = apply_setback(plot_polygon, setback)
        return {
            "feasible": True,
            "original_area_sqm": plot_polygon.area,
            "estimated_buildable_sqm": buildable.area,
        }
    except SetbackError as exc:
        return {
            "feasible": False,
            "original_area_sqm": plot_polygon.area,
            "estimated_buildable_sqm": 0.0,
            "error": str(exc),
        }
