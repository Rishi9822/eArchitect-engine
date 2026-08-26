"""
Circulation analysis — graph-based room connectivity model.

Builds a room adjacency graph using shared walls, doors, and
entrance connections, then evaluates reachability and dead ends.
"""
from __future__ import annotations

import logging
from typing import List, Dict, Set, Optional, Tuple
from collections import defaultdict, deque

from shapely.geometry import Polygon

from ..geometry.polygon_utils import polygons_share_boundary

logger = logging.getLogger(__name__)


def build_adjacency_graph(
    room_polygons: Dict[str, Polygon],
    doors: List[dict],
    entrance: Optional[dict],
) -> Dict[str, Set[str]]:
    """
    Build an undirected room connectivity graph.

    Edges are created from:
    1. Shared boundaries between room polygons
    2. Doors connecting rooms
    3. Entrance connecting to a room

    Returns:
        Adjacency dict: {room_id: set of connected room_ids}
    """
    graph: Dict[str, Set[str]] = defaultdict(set)
    room_ids = list(room_polygons.keys())

    # Ensure all rooms are in the graph
    for rid in room_ids:
        graph[rid]  # creates empty set

    # 1. Shared boundaries (geometric adjacency)
    for i in range(len(room_ids)):
        for j in range(i + 1, len(room_ids)):
            id_a, id_b = room_ids[i], room_ids[j]
            if polygons_share_boundary(
                room_polygons[id_a], room_polygons[id_b],
                min_length=0.1,
            ):
                graph[id_a].add(id_b)
                graph[id_b].add(id_a)

    # 2. Doors (explicit connections)
    for door in doors:
        from_r = door.get("from_room")
        to_r = door.get("to_room")
        if from_r and to_r:
            graph[from_r].add(to_r)
            graph[to_r].add(from_r)

    # 3. Entrance (connect entrance room to a virtual "ENTRANCE" node)
    if entrance:
        ent_room = entrance.get("room_id")
        if ent_room and ent_room in graph:
            graph["ENTRANCE"].add(ent_room)
            graph[ent_room].add("ENTRANCE")

    return dict(graph)


def analyze_circulation(
    graph: Dict[str, Set[str]],
    room_ids: List[str],
    entrance_room_id: Optional[str] = None,
) -> dict:
    """
    Analyze circulation connectivity.

    Determines:
    - Whether all rooms are reachable from the entrance
    - Number of dead ends (rooms with only one connection)
    - Graph connectivity

    Returns:
        Circulation analysis dict
    """
    total_rooms = len(room_ids)

    if total_rooms == 0:
        return {
            "connected": True,
            "reachable_rooms": 0,
            "total_rooms": 0,
            "dead_ends": 0,
            "graph_edges": 0,
            "score": 1.0,
        }

    # BFS from entrance or from first room
    start = "ENTRANCE" if "ENTRANCE" in graph else (
        entrance_room_id if entrance_room_id else room_ids[0]
    )

    visited: Set[str] = set()
    queue: deque = deque([start])
    visited.add(start)

    while queue:
        node = queue.popleft()
        for neighbor in graph.get(node, set()):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)

    # Count reachable actual rooms (exclude ENTRANCE virtual node)
    reachable = sum(1 for rid in room_ids if rid in visited)

    # Count dead ends (rooms with only 1 connection, excluding ENTRANCE)
    dead_ends = 0
    for rid in room_ids:
        connections = graph.get(rid, set())
        real_connections = connections - {"ENTRANCE"}
        if len(real_connections) <= 1 and rid != entrance_room_id:
            dead_ends += 1

    # Count graph edges
    edge_count = sum(len(v) for v in graph.values()) // 2

    # Connectivity score
    connected = reachable >= total_rooms

    # Score: combination of reachability and dead-end ratio
    reachability_score = reachable / total_rooms if total_rooms > 0 else 1.0

    dead_end_penalty = 0.0
    if total_rooms > 1:
        # Moderate dead-end ratio is acceptable (bedrooms are often dead ends)
        dead_end_ratio = dead_ends / total_rooms
        if dead_end_ratio > 0.7:
            dead_end_penalty = 0.3
        elif dead_end_ratio > 0.5:
            dead_end_penalty = 0.15

    score = max(0.0, reachability_score - dead_end_penalty)

    return {
        "connected": connected,
        "reachable_rooms": reachable,
        "total_rooms": total_rooms,
        "dead_ends": dead_ends,
        "graph_edges": edge_count,
        "score": round(score, 4),
    }
