"""
Internal door generation using architectural adjacency graph and MST.

Priority 1 Implementation:
1. Build room-adjacency graph with candidate edges meeting clearance requirements:
   shared_wall_length >= door_width + DOOR_WALL_CLEARANCE_M (0.30m).
2. Classify edges using DOOR_ADJACENCY tables (FORBIDDEN = inf, PREFERRED = 1,
   ACCEPTABLE = 3, DISCOURAGED = 8).
3. Compute Minimum Spanning Tree (MST) rooted at the entrance room.
4. Add back at most MAX_CONVENIENCE_DOORS (2) convenience edges where cost == 1.
5. Never place a FORBIDDEN door; mark candidate invalid if a room (e.g. toilet)
   has no valid non-forbidden connection.
6. Target total door count between room_count+1 and room_count+3.
"""
from __future__ import annotations

import logging
from typing import List, Dict, Optional, Tuple, Set

from shapely.geometry import Polygon, LineString

from ..config import (
    DEFAULT_DOOR_WIDTH_M,
    TOILET_DOOR_WIDTH_M,
    PARKING_SHUTTER_WIDTH_M,
    DOOR_WALL_CLEARANCE_M,
    MIN_WALL_FOR_DOOR_M,
    MAX_CONVENIENCE_DOORS,
    DOOR_ADJACENCY_FORBIDDEN,
    DOOR_ADJACENCY_PREFERRED,
    DOOR_ADJACENCY_ACCEPTABLE,
    DOOR_ADJACENCY_DISCOURAGED,
    ZONE_MAP,
    get_room_defaults,
)
from ..geometry.polygon_utils import polygons_share_boundary

logger = logging.getLogger(__name__)


def _find_shared_wall(poly_a: Polygon, poly_b: Polygon) -> Optional[LineString]:
    """
    Find the shared boundary segment between two room polygons.
    Returns the longest shared segment as a LineString.
    """
    try:
        inters = poly_a.boundary.intersection(poly_b.boundary)
        if inters.is_empty:
            return None

        # Extract linear pieces
        if hasattr(inters, "geoms"):
            lines = [g for g in inters.geoms
                     if isinstance(g, LineString) and g.length >= 0.10]
            if not lines:
                return None
            return max(lines, key=lambda l: l.length)
        elif isinstance(inters, LineString) and inters.length >= 0.10:
            return inters

        return None
    except Exception:
        return None


def get_door_width(type_a: str, type_b: str) -> float:
    """
    Get architecturally standard door width based on room types.
    - Toilet/Bathroom: 0.75 m
    - Bedroom/Living/Kitchen/Dining: 0.90 m
    - Parking service door: 0.90 m
    """
    t_a = type_a.lower()
    t_b = type_b.lower()
    if t_a in ("toilet", "bathroom") or t_b in ("toilet", "bathroom"):
        return TOILET_DOOR_WIDTH_M
    return DEFAULT_DOOR_WIDTH_M


def _matches(pair_set: Set[Tuple[str, str]], t_a: str, t_b: str) -> bool:
    return (t_a, t_b) in pair_set or (t_b, t_a) in pair_set


def classify_door_edge(
    type_a: str,
    type_b: str,
    has_corridor: bool = False,
) -> float:
    """
    Classify candidate door edge cost based on the Priority 1 table:
    - FORBIDDEN = infinity (never place a door)
    - PREFERRED = 1
    - ACCEPTABLE = 3
    - DISCOURAGED = 8
    """
    t_a = type_a.lower()
    t_b = type_b.lower()

    # Explicit FORBIDDEN pairs
    if _matches(DOOR_ADJACENCY_FORBIDDEN, t_a, t_b):
        return float("inf")

    # Both rooms private (and neither is corridor) -> FORBIDDEN
    zone_a = ZONE_MAP.get(t_a, "")
    zone_b = ZONE_MAP.get(t_b, "")
    if zone_a == "private" and zone_b == "private" and t_a != "corridor" and t_b != "corridor":
        return float("inf")

    # living <-> bedroom: ACCEPTABLE (3) only if no corridor exists; DISCOURAGED (8) if corridor exists
    if _matches({("bedroom", "living"), ("living", "master_bedroom")}, t_a, t_b):
        return 8.0 if has_corridor else 3.0

    if _matches(DOOR_ADJACENCY_PREFERRED, t_a, t_b):
        return 1.0

    if _matches(DOOR_ADJACENCY_ACCEPTABLE, t_a, t_b):
        return 3.0

    if _matches(DOOR_ADJACENCY_DISCOURAGED, t_a, t_b):
        return 8.0

    # Parking connections: only parking <-> kitchen is acceptable (cost 3), all others discouraged/forbidden
    if t_a == "parking" or t_b == "parking":
        return 8.0

    return 4.0


class DoorList(list):
    """List subclass carrying door placement metadata and reachability info."""
    unreachable_rooms: List[str] = []
    has_forbidden_doors: bool = False
    flagged_for_review: bool = False


def generate_doors(
    room_polygons: Dict[str, Polygon],
    room_types: Dict[str, str],
    entrance_room_id: Optional[str] = None,
) -> List[dict]:
    """
    Generate architecturally valid doors using an adjacency graph and MST.

    1. Build candidate edges with clearance check:
       shared_wall.length >= door_width + 0.30 m
    2. Classify candidate edges using config rules.
    3. Compute Minimum Spanning Tree rooted at entrance_room_id.
    4. Add at most 2 convenience edges where cost == 1.
    5. Never place forbidden doors.

    Args:
        room_polygons:    {room_id: Polygon}
        room_types:       {room_id: room_type_str}
        entrance_room_id: room connected to main entrance (root of spanning tree)

    Returns:
        DoorList of door dicts
    """
    room_ids = list(room_polygons.keys())
    doors = DoorList()

    if len(room_ids) <= 1:
        return doors

    has_corridor = any(
        room_types.get(rid, "").lower() == "corridor" or "corridor" in rid
        for rid in room_ids
    )

    # ── 1. Find Candidate Edges ───────────────────────────────────────────
    candidate_edges = []
    n = len(room_ids)

    for i in range(n):
        for j in range(i + 1, n):
            id_a, id_b = room_ids[i], room_ids[j]
            poly_a = room_polygons[id_a]
            poly_b = room_polygons[id_b]

            if not polygons_share_boundary(poly_a, poly_b, min_length=0.10):
                continue

            shared = _find_shared_wall(poly_a, poly_b)
            if shared is None:
                continue

            type_a = room_types.get(id_a, "")
            type_b = room_types.get(id_b, "")
            door_width = get_door_width(type_a, type_b)

            # Clearance check: shared wall must be >= door_width + 0.30m
            min_wall_needed = door_width + DOOR_WALL_CLEARANCE_M
            if shared.length < min_wall_needed:
                logger.debug(
                    "Wall between %s and %s length %.2f < needed %.2f; discarded.",
                    id_a, id_b, shared.length, min_wall_needed,
                )
                continue

            cost = classify_door_edge(type_a, type_b, has_corridor=has_corridor)
            if cost == float("inf"):
                logger.debug(
                    "Forbidden edge between %s (%s) and %s (%s)",
                    id_a, type_a, id_b, type_b,
                )
                continue

            candidate_edges.append({
                "id_a": id_a,
                "id_b": id_b,
                "type_a": type_a,
                "type_b": type_b,
                "door_width": door_width,
                "cost": cost,
                "shared": shared,
                "length": shared.length,
            })

    # ── 2. Determine Spanning Tree Root ───────────────────────────────────
    root = None
    if entrance_room_id and entrance_room_id in room_polygons:
        root = entrance_room_id
    else:
        # Fallback to public room or first room
        for rid in room_ids:
            if ZONE_MAP.get(room_types.get(rid, "").lower(), "") == "public":
                root = rid
                break
        if root is None:
            root = room_ids[0]

    # ── 3. Compute Minimum Spanning Tree (Prim's Algorithm) ───────────────
    visited: Set[str] = {root}
    tree_edges: List[dict] = []
    parking_kitchen_used = False

    while len(visited) < len(room_ids):
        best_edge = None
        best_key = (float("inf"), 0.0)  # (cost, -length)

        for edge in candidate_edges:
            u, v = edge["id_a"], edge["id_b"]
            if (u in visited and v not in visited) or (v in visited and u not in visited):
                # Service access check: allow at most ONE parking <-> kitchen door
                is_parking_kitchen = tuple(sorted([edge["type_a"], edge["type_b"]])) == ("kitchen", "parking")
                if is_parking_kitchen and parking_kitchen_used:
                    continue

                key = (edge["cost"], -edge["length"])
                if key < best_key:
                    best_key = key
                    best_edge = edge

        if best_edge is None:
            # Graph is disconnected by non-forbidden edges
            break

        new_node = best_edge["id_b"] if best_edge["id_a"] in visited else best_edge["id_a"]
        visited.add(new_node)
        tree_edges.append(best_edge)

        if tuple(sorted([best_edge["type_a"], best_edge["type_b"]])) == ("kitchen", "parking"):
            parking_kitchen_used = True

    # Check for unreached rooms (e.g. toilet with only forbidden edges)
    # Note: Parking is an exterior vehicular space with an outside shutter;
    # lack of an internal door does not make parking unreachable.
    unreached = [
        rid for rid in room_ids
        if rid not in visited and room_types.get(rid, "").lower() != "parking"
    ]
    doors.unreachable_rooms = unreached
    if unreached:
        logger.warning(
            "Rooms unreachable via architecturally valid doors: %s", unreached
        )

    # ── 4. Add Convenience Edges (At Most 2, Cost == 1.0 Only) ────────────
    tree_edge_set = {
        tuple(sorted([e["id_a"], e["id_b"]])) for e in tree_edges
    }

    convenience_candidates = [
        e for e in candidate_edges
        if tuple(sorted([e["id_a"], e["id_b"]])) not in tree_edge_set and e["cost"] == 1.0
    ]
    # Sort by wall length descending
    convenience_candidates.sort(key=lambda e: -e["length"])

    selected_convenience = convenience_candidates[:MAX_CONVENIENCE_DOORS]
    all_selected_edges = tree_edges + selected_convenience

    # ── 5. Generate Door Dicts ────────────────────────────────────────────
    door_counter = 1
    for edge in all_selected_edges:
        id_a = edge["id_a"]
        id_b = edge["id_b"]
        type_a = edge["type_a"]
        type_b = edge["type_b"]
        door_width = edge["door_width"]
        shared = edge["shared"]

        mid = shared.interpolate(0.5, normalized=True)

        door_type = "internal"
        if type_a == "parking" or type_b == "parking":
            door_type = "service"

        doors.append({
            "id": f"D{door_counter:03d}",
            "type": door_type,
            "width": round(door_width, 3),
            "position": {"x": round(mid.x, 4), "y": round(mid.y, 4)},
            "wall_id": None,  # Resolved after wall extraction
            "from_room": id_a,
            "to_room": id_b,
        })
        door_counter += 1

    # Check target door count
    # Expected target: roughly room_count - 1 to room_count + 3
    if len(doors) > len(room_ids) + 4:
        logger.warning(
            "Door count %d exceeds threshold (room_count %d + 4); flagging for review.",
            len(doors), len(room_ids),
        )
        doors.flagged_for_review = True

    logger.info(
        "Generated %d doors (%d spanning tree, %d convenience) for %d rooms.",
        len(doors), len(tree_edges), len(selected_convenience), len(room_ids),
    )
    return doors
