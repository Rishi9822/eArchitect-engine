"""
Architectural quality metrics.

Computes natural light, ventilation, dead space efficiency,
and constraint compliance scores.
"""
from __future__ import annotations

import logging
from typing import List, Dict

from shapely.geometry import Polygon

from ..config import (
    DEAD_SPACE_PENALTIES,
    SQ_M_TO_SQ_FT,
    get_room_defaults,
)
from ..geometry.polygon_utils import polygon_exterior_contact

logger = logging.getLogger(__name__)


def score_natural_light(
    room_polygons: Dict[str, Polygon],
    room_types: Dict[str, str],
    inner_polygon: Polygon,
    windows: List[dict],
) -> float:
    """
    Score natural light availability.

    For rooms that require natural light (bedroom, living, dining):
    - Check exterior wall contact
    - Check window placement

    Returns: 0.0 to 1.0
    """
    light_rooms = []

    for room_id, poly in room_polygons.items():
        rtype = room_types.get(room_id, "").lower()
        defaults = get_room_defaults(rtype)
        if defaults.requires_natural_light:
            light_rooms.append(room_id)

    if not light_rooms:
        return 1.0

    satisfied = 0
    for room_id in light_rooms:
        poly = room_polygons[room_id]

        # Check exterior wall contact
        ext_contact = polygon_exterior_contact(poly, inner_polygon, min_length=0.5)
        has_exterior = ext_contact >= 0.5

        # Check if room has a window
        has_window = any(w.get("room_id") == room_id for w in windows)

        if has_exterior and has_window:
            satisfied += 1
        elif has_exterior:
            satisfied += 0.5

    return satisfied / len(light_rooms)


def score_ventilation(
    room_polygons: Dict[str, Polygon],
    room_types: Dict[str, str],
    inner_polygon: Polygon,
    windows: List[dict],
) -> float:
    """
    Score ventilation availability.

    For rooms that require ventilation:
    - Check exterior wall contact or window presence

    Returns: 0.0 to 1.0
    """
    vent_rooms = []

    for room_id, poly in room_polygons.items():
        rtype = room_types.get(room_id, "").lower()
        defaults = get_room_defaults(rtype)
        if defaults.requires_ventilation:
            vent_rooms.append(room_id)

    if not vent_rooms:
        return 1.0

    satisfied = 0
    for room_id in vent_rooms:
        poly = room_polygons[room_id]

        ext_contact = polygon_exterior_contact(poly, inner_polygon, min_length=0.3)
        has_exterior = ext_contact >= 0.3
        has_window = any(w.get("room_id") == room_id for w in windows)

        if has_window:
            satisfied += 1
        elif has_exterior:
            satisfied += 0.7

    return satisfied / len(vent_rooms)


def score_dead_space(
    dead_spaces: List[dict],
    inner_polygon: Polygon,
) -> float:
    """
    Score dead space efficiency.

    Different dead space types have different penalty weights.
    Score = 1.0 - weighted_penalty

    Returns: 0.0 to 1.0
    """
    if not dead_spaces:
        return 1.0

    buildable_area = inner_polygon.area
    if buildable_area <= 0:
        return 1.0

    total_penalty = 0.0
    for ds in dead_spaces:
        area_sqm = ds.get("area_sqm", ds.get("area_sqft", 0) / SQ_M_TO_SQ_FT)
        classification = ds.get("classification", "unusable")
        weight = DEAD_SPACE_PENALTIES.get(classification, 0.5)
        total_penalty += (area_sqm / buildable_area) * weight

    return max(0.0, 1.0 - total_penalty)


def score_parking_accessibility(
    parking_entities: List[dict],
) -> float:
    """
    Score parking accessibility.

    Returns: 0.0 to 1.0
    """
    if not parking_entities:
        return 1.0  # No parking needed, neutral

    total = len(parking_entities)
    good = 0

    for p in parking_entities:
        score = 0.0
        if p.get("meets_minimum", False):
            score += 0.5
        if p.get("road_access", False):
            score += 0.5
        good += score

    return good / total if total > 0 else 1.0


def score_constraint_compliance(
    validation_warnings: List[dict],
    validation_errors: List[dict],
    total_rooms: int,
) -> float:
    """
    Score overall constraint compliance.

    Errors reduce score heavily, warnings moderately.

    Returns: 0.0 to 1.0
    """
    if total_rooms <= 0:
        return 0.0

    error_penalty = len(validation_errors) * 0.2
    warning_penalty = len(validation_warnings) * 0.05

    return max(0.0, 1.0 - error_penalty - warning_penalty)
