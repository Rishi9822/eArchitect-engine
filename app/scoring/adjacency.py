"""
Room-level adjacency scoring.

Evaluates room adjacency based on PREFERRED_ADJACENCY_PAIRS,
measuring the fraction of achievable preferred room-type pairs
that are actually connected by a door (or corridor).
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

from shapely.geometry import Polygon

from ..config import (
    ADJACENCY_RULES,
    PREFERRED_ZONE_ADJACENCY,
    PREFERRED_ADJACENCY_PAIRS,
    ZONE_MAP,
)
from ..geometry.polygon_utils import polygons_share_boundary

logger = logging.getLogger(__name__)



def compute_room_adjacency(
    room_polygons: Dict[str, Polygon],
    room_types: Dict[str, str],
) -> Dict[str, Set[str]]:
    """
    Build room adjacency map from geometric proximity.

    Returns:
        {room_id: set of adjacent room_ids}
    """
    adjacency: Dict[str, Set[str]] = {rid: set() for rid in room_polygons}
    room_ids = list(room_polygons.keys())

    for i in range(len(room_ids)):
        for j in range(i + 1, len(room_ids)):
            id_a, id_b = room_ids[i], room_ids[j]
            if polygons_share_boundary(
                room_polygons[id_a], room_polygons[id_b],
                min_length=0.1,
            ):
                adjacency[id_a].add(id_b)
                adjacency[id_b].add(id_a)

    return adjacency


def score_adjacency(
    room_polygons: Dict[str, Polygon],
    room_types: Dict[str, str],
    zone_polygons: Optional[Dict[str, Polygon]] = None,
    doors: Optional[List[dict]] = None,
    corridors: Optional[List[dict]] = None,
    corridor_polygons: Optional[List[Polygon]] = None,
    return_breakdown: bool = False,
) -> float | Tuple[float, List[Dict[str, Any]]]:
    """
    Score room-level adjacency quality based on PREFERRED adjacency pairs.

    Evaluates the fraction of PREFERRED adjacency pairs that are actually
    adjacent AND connected by a door or corridor, out of all PREFERRED
    pairs achievable given the room program.

    Args:
        room_polygons:     {room_id: Polygon}
        room_types:        {room_id: type_str}
        zone_polygons:     Optional zone-level polygons
        doors:             List of door dicts
        corridors:         List of corridor dicts
        corridor_polygons: List of corridor Polygons
        return_breakdown:  If True, returns (score, breakdown_list)

    Returns:
        score: float (0.0 to 1.0)
        or (score, adjacency_breakdown) if return_breakdown is True.
    """
    present_types = {t.lower() for t in room_types.values()}
    has_corridor = any("corridor" in t.lower() for t in present_types) or bool(corridors)
    if has_corridor:
        present_types.add("corridor")

    # Build door pairs lookup
    door_pairs: Set[Tuple[str, str]] = set()
    if doors is not None:
        for d in doors:
            fr = d.get("from_room")
            to = d.get("to_room")
            if fr and to:
                door_pairs.add((fr, to))
                door_pairs.add((to, fr))

    # Build corridor connectivity lookup
    rooms_connected_to_corridor: Dict[str, Set[str]] = defaultdict(set)
    if corridors:
        for corr_data in corridors:
            cid = corr_data.get("id", "corridor_0")
            if doors is not None:
                for d in doors:
                    fr = d.get("from_room")
                    to = d.get("to_room")
                    if fr == cid and to:
                        rooms_connected_to_corridor[cid].add(to)
                    elif to == cid and fr:
                        rooms_connected_to_corridor[cid].add(fr)
            elif corridor_polygons:
                for rid, poly in room_polygons.items():
                    for cpoly in corridor_polygons:
                        if polygons_share_boundary(cpoly, poly, min_length=0.1):
                            rooms_connected_to_corridor[cid].add(rid)

    breakdown: List[Dict[str, Any]] = []

    for t_a, t_b in PREFERRED_ADJACENCY_PAIRS:
        # Check if achievable given room program
        if t_a not in present_types or t_b not in present_types:
            continue
        if t_a == t_b:
            if sum(1 for t in room_types.values() if t.lower() == t_a) < 2:
                continue

        # Find room IDs for type t_a and t_b
        if t_a == "corridor":
            rooms_a = [c.get("id", "corridor_0") for c in (corridors or [])] or [
                r for r, t in room_types.items() if "corridor" in t.lower()
            ]
        else:
            rooms_a = [r for r, t in room_types.items() if t.lower() == t_a]

        if t_b == "corridor":
            rooms_b = [c.get("id", "corridor_0") for c in (corridors or [])] or [
                r for r, t in room_types.items() if "corridor" in t.lower()
            ]
        else:
            rooms_b = [r for r, t in room_types.items() if t.lower() == t_b]

        achieved = False
        for r_a in rooms_a:
            for r_b in rooms_b:
                if r_a == r_b:
                    continue

                poly_a = room_polygons.get(r_a)
                poly_b = room_polygons.get(r_b)
                is_adjacent = False
                if poly_a is not None and poly_b is not None:
                    is_adjacent = polygons_share_boundary(poly_a, poly_b, min_length=0.1)

                # Condition 1: Adjacent AND connected by a door
                if doors is not None:
                    has_door = (r_a, r_b) in door_pairs
                    if is_adjacent and has_door:
                        achieved = True
                        break
                else:
                    # Pre-door fallback: adjacent is sufficient
                    if is_adjacent:
                        achieved = True
                        break

                # Condition 2: Both connected to the same corridor
                for cid, connected_rooms in rooms_connected_to_corridor.items():
                    if r_a in connected_rooms and r_b in connected_rooms:
                        achieved = True
                        break
                if achieved:
                    break

            if achieved:
                break

        breakdown.append({
            "pair": [t_a, t_b],
            "satisfied": achieved,
        })

    if breakdown:
        score = sum(1 for item in breakdown if item["satisfied"]) / len(breakdown)
    else:
        score = 1.0

    score = round(score, 4)

    if return_breakdown:
        return score, breakdown
    return score

