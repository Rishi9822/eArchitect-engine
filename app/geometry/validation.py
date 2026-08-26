"""
Plot geometry validation.

Validates input plot polygons before BSP generation.
Returns structured validation results with error codes.
"""
from __future__ import annotations

import math
import logging
from typing import List, Tuple, Optional
from dataclasses import dataclass, field

from shapely.geometry import Polygon
from shapely.validation import explain_validity

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of geometry validation."""
    valid: bool = True
    errors: List[dict] = field(default_factory=list)
    warnings: List[dict] = field(default_factory=list)

    def add_error(self, code: str, message: str, **details):
        self.valid = False
        self.errors.append({"code": code, "message": message, **details})

    def add_warning(self, code: str, message: str, **details):
        self.warnings.append({"code": code, "message": message, **details})


def validate_plot_geometry(
    points: List[Tuple[float, float]],
) -> ValidationResult:
    """
    Comprehensive validation of a plot polygon before BSP generation.

    Checks:
    - At least 3 points
    - Distinct points (no duplicates)
    - No zero-length edges
    - Finite coordinate values (no NaN, no Inf)
    - Valid Shapely polygon
    - Not self-intersecting
    - Non-zero area
    - Polygon orientation (CCW)
    - Reasonable edge lengths
    """
    result = ValidationResult()

    # ── 1. Minimum point count ─────────────────────────────────────
    if len(points) < 3:
        result.add_error(
            "INVALID_PLOT",
            f"Plot requires at least 3 points, got {len(points)}",
            point_count=len(points),
        )
        return result

    # ── 2. Finite coordinates ──────────────────────────────────────
    for i, (x, y) in enumerate(points):
        if not (math.isfinite(x) and math.isfinite(y)):
            result.add_error(
                "INVALID_PLOT",
                f"Point {i} has non-finite coordinates: ({x}, {y})",
                point_index=i,
            )
    if not result.valid:
        return result

    # ── 3. Distinct points ─────────────────────────────────────────
    unique = set(points)
    if len(unique) < 3:
        result.add_error(
            "INVALID_PLOT",
            f"Plot must have at least 3 distinct points, got {len(unique)} unique out of {len(points)}",
            distinct_count=len(unique),
        )
        return result

    # Remove consecutive duplicates
    cleaned: List[Tuple[float, float]] = [points[0]]
    for i in range(1, len(points)):
        if points[i] != points[i - 1]:
            cleaned.append(points[i])
    if len(cleaned) > 1 and cleaned[-1] == cleaned[0]:
        cleaned = cleaned[:-1]

    if len(cleaned) < 3:
        result.add_error(
            "INVALID_PLOT",
            "After removing duplicate consecutive points, fewer than 3 remain",
        )
        return result

    # ── 4. Zero-length edges ───────────────────────────────────────
    for i in range(len(cleaned)):
        j = (i + 1) % len(cleaned)
        dx = cleaned[j][0] - cleaned[i][0]
        dy = cleaned[j][1] - cleaned[i][1]
        edge_len = math.sqrt(dx * dx + dy * dy)
        if edge_len < 1e-6:
            result.add_error(
                "INVALID_PLOT",
                f"Zero-length edge between point {i} and point {j}",
                edge_index=i,
            )
    if not result.valid:
        return result

    # ── 5. Build Shapely polygon and validate ──────────────────────
    try:
        poly = Polygon(cleaned)
    except Exception as exc:
        result.add_error(
            "INVALID_PLOT",
            f"Failed to create polygon: {exc}",
        )
        return result

    if poly.is_empty:
        result.add_error("INVALID_PLOT", "Polygon is empty")
        return result

    if not poly.is_valid:
        reason = explain_validity(poly)
        result.add_error(
            "INVALID_PLOT",
            f"Polygon is not valid: {reason}",
            shapely_reason=reason,
        )
        return result

    # ── 6. Self-intersection check ─────────────────────────────────
    if not poly.is_simple:
        result.add_error(
            "INVALID_PLOT",
            "Polygon is self-intersecting",
        )
        return result

    # ── 7. Non-zero area ───────────────────────────────────────────
    if poly.area < 1e-6:
        result.add_error(
            "INVALID_PLOT",
            f"Polygon has zero or near-zero area: {poly.area}",
            area=poly.area,
        )
        return result

    # ── 8. Orientation check (warn if CW) ──────────────────────────
    if not poly.exterior.is_ccw:
        result.add_warning(
            "PLOT_ORIENTATION",
            "Polygon exterior ring is clockwise; will be normalised to CCW",
        )

    # ── 9. Reasonable edge lengths ─────────────────────────────────
    coords = list(poly.exterior.coords)
    for i in range(len(coords) - 1):
        dx = coords[i + 1][0] - coords[i][0]
        dy = coords[i + 1][1] - coords[i][1]
        edge_len = math.sqrt(dx * dx + dy * dy)
        if edge_len < 0.1:
            result.add_warning(
                "SHORT_EDGE",
                f"Edge {i} is very short ({edge_len:.3f} m)",
                edge_index=i,
                edge_length=edge_len,
            )
        if edge_len > 500:
            result.add_warning(
                "LONG_EDGE",
                f"Edge {i} is unusually long ({edge_len:.1f} m)",
                edge_index=i,
                edge_length=edge_len,
            )

    # ── 10. Reasonable area check ──────────────────────────────────
    area_sqm = poly.area
    if area_sqm < 10:
        result.add_warning(
            "SMALL_PLOT",
            f"Plot area is very small ({area_sqm:.2f} sqm)",
            area_sqm=area_sqm,
        )
    if area_sqm > 100000:
        result.add_warning(
            "LARGE_PLOT",
            f"Plot area is very large ({area_sqm:.0f} sqm)",
            area_sqm=area_sqm,
        )

    return result
