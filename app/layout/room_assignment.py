"""
Room assignment validation and completeness checking.

After BSP generation, validates every room-to-leaf assignment
against hard constraints: area, width, aspect ratio, containment,
and overlap.
"""
from __future__ import annotations

import logging
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field

from shapely.geometry import Polygon

from ..config import SQ_M_TO_SQ_FT
from ..geometry.polygon_utils import aspect_ratio, min_dimension, max_dimension
from .bsp import RoomSpec, BSPNode

logger = logging.getLogger(__name__)


@dataclass
class ConstraintViolation:
    """A single constraint violation for a room."""
    room_id: str
    room_type: str
    constraint: str
    required: float
    actual: float
    message: str


@dataclass
class AssignmentValidation:
    """Result of room assignment validation."""
    valid: bool = True
    violations: List[ConstraintViolation] = field(default_factory=list)
    warnings: List[ConstraintViolation] = field(default_factory=list)
    missing_rooms: List[str] = field(default_factory=list)
    overlap_pairs: List[Tuple[str, str]] = field(default_factory=list)


def validate_room_assignment(
    room_leaves: Dict[str, BSPNode],
    all_specs: List[RoomSpec],
    inner_polygon: Polygon,
    strict: bool = False,
) -> AssignmentValidation:
    """
    Validate all room-to-leaf assignments.

    Checks:
    1. Room completeness — all requested rooms are placed
    2. Area — room area >= min_area_sqm
    3. Width — room min dimension >= min_width_m
    4. Aspect ratio — within max_aspect_ratio
    5. Containment — room is inside buildable area
    6. Overlap — no two rooms overlap (interior intersection)

    Args:
        room_leaves:    dict of room_id → BSPNode
        all_specs:      all requested RoomSpec objects
        inner_polygon:  buildable area polygon
        strict:         if True, min area violations are errors; else warnings

    Returns:
        AssignmentValidation with violations and warnings
    """
    result = AssignmentValidation()

    # ── 1. Completeness ──────────────────────────────────────────
    placed_ids = set(room_leaves.keys())
    for spec in all_specs:
        if spec.id not in placed_ids:
            result.missing_rooms.append(spec.id)
            result.violations.append(ConstraintViolation(
                room_id=spec.id,
                room_type=spec.type,
                constraint="ROOM_MISSING",
                required=1,
                actual=0,
                message=f"Room '{spec.id}' ({spec.type}) was not placed",
            ))

    if result.missing_rooms:
        result.valid = False

    # ── 2. Per-room constraint checks ────────────────────────────
    room_polys: Dict[str, Polygon] = {}

    for room_id, leaf in room_leaves.items():
        spec = leaf.room
        if spec is None:
            continue

        poly = leaf.polygon
        room_polys[room_id] = poly

        # 2a. Polygon validity
        if not poly.is_valid or poly.is_empty:
            result.violations.append(ConstraintViolation(
                room_id=room_id, room_type=spec.type,
                constraint="GEOMETRY_INVALID",
                required=0, actual=0,
                message=f"Room '{room_id}' has invalid geometry",
            ))
            result.valid = False
            continue

        # 2b. Area check
        area_sqm = poly.area
        if area_sqm < spec.min_area_sqm:
            deficit_pct = (1 - area_sqm / spec.min_area_sqm) * 100
            violation = ConstraintViolation(
                room_id=room_id, room_type=spec.type,
                constraint="ROOM_AREA_INFEASIBLE",
                required=round(spec.min_area_sqm, 4),
                actual=round(area_sqm, 4),
                message=(
                    f"Room '{room_id}' area {area_sqm * SQ_M_TO_SQ_FT:.1f} sqft "
                    f"is {deficit_pct:.1f}% below minimum "
                    f"{spec.min_area_sqm * SQ_M_TO_SQ_FT:.1f} sqft"
                ),
            )
            if strict or deficit_pct > 30:
                result.violations.append(violation)
                result.valid = False
            else:
                result.warnings.append(violation)

        # 2c. Width check
        if spec.min_width_m > 0:
            md = min_dimension(poly)
            if md < spec.min_width_m * 0.8:
                result.warnings.append(ConstraintViolation(
                    room_id=room_id, room_type=spec.type,
                    constraint="ROOM_DIMENSION_INFEASIBLE",
                    required=round(spec.min_width_m, 3),
                    actual=round(md, 3),
                    message=(
                        f"Room '{room_id}' min dimension {md:.2f}m "
                        f"below minimum {spec.min_width_m:.2f}m"
                    ),
                ))

        # 2d. Aspect ratio check
        ar = aspect_ratio(poly)
        if ar > spec.max_aspect_ratio:
            result.warnings.append(ConstraintViolation(
                room_id=room_id, room_type=spec.type,
                constraint="ROOM_ASPECT_RATIO",
                required=spec.max_aspect_ratio,
                actual=round(ar, 3),
                message=(
                    f"Room '{room_id}' aspect ratio {ar:.2f} "
                    f"exceeds maximum {spec.max_aspect_ratio}"
                ),
            ))

        # 2e. Containment check
        if not inner_polygon.contains(poly):
            # Check how much is outside
            outside = poly.difference(inner_polygon)
            if not outside.is_empty and outside.area > poly.area * 0.05:
                result.warnings.append(ConstraintViolation(
                    room_id=room_id, room_type=spec.type,
                    constraint="ROOM_OUTSIDE_BOUNDARY",
                    required=0,
                    actual=round(outside.area, 4),
                    message=(
                        f"Room '{room_id}' extends {outside.area:.3f} sqm "
                        f"outside buildable boundary"
                    ),
                ))

    # ── 3. Overlap check ─────────────────────────────────────────
    room_ids = list(room_polys.keys())
    for i in range(len(room_ids)):
        for j in range(i + 1, len(room_ids)):
            id_a, id_b = room_ids[i], room_ids[j]
            poly_a, poly_b = room_polys[id_a], room_polys[id_b]

            if not poly_a.intersects(poly_b):
                continue

            intersection = poly_a.intersection(poly_b)
            if intersection.is_empty:
                continue

            # Touching at boundary is OK; interior overlap is not
            overlap_area = intersection.area
            if overlap_area > 0.01:  # >0.01 sqm = real overlap
                result.overlap_pairs.append((id_a, id_b))
                result.warnings.append(ConstraintViolation(
                    room_id=id_a, room_type="",
                    constraint="GEOMETRY_OVERLAP",
                    required=0,
                    actual=round(overlap_area, 4),
                    message=(
                        f"Rooms '{id_a}' and '{id_b}' overlap by "
                        f"{overlap_area:.3f} sqm"
                    ),
                ))

    return result
