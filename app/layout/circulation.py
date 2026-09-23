"""
Circulation analysis — graph-based room connectivity model.

Builds a room adjacency graph using doors (or fallback shared boundaries)
and entrance connections, evaluates reachability, and calculates a weighted
composite circulation quality score.
"""
from __future__ import annotations

import logging
from typing import List, Dict, Set, Optional, Tuple
from collections import defaultdict, deque

from shapely.geometry import Polygon

from ..config import ZONE_MAP
from ..geometry.polygon_utils import polygons_share_boundary

logger = logging.getLogger(__name__)


def build_adjacency_graph(
    room_polygons: Dict[str, Polygon],
    doors: List[dict],
    entrance: Optional[dict],
    corridors: Optional[List[dict]] = None,
    corridor_polygons: Optional[List[Polygon]] = None,
) -> Dict[str, Set[str]]:
    """
    Build an undirected room connectivity graph.

    Edges are created from:
    1. Doors connecting rooms (if doors provided)
    2. Shared boundaries (fallback only if no doors provided)
    3. Entrance connecting to entrance room
    4. Corridors connecting to adjacent rooms

    Returns:
        Adjacency dict: {room_id: set of connected room_ids}
    """
    graph: Dict[str, Set[str]] = defaultdict(set)
    room_ids = list(room_polygons.keys())

    # Ensure all rooms are in the graph
    for rid in room_ids:
        graph[rid]  # creates empty set

    # Corridors: ensure corridor nodes exist in graph
    if corridors:
        for corr_data in corridors:
            corr_id = corr_data.get("id", "corridor_0")
            graph[corr_id]

    if doors:
        # Explicit door connections define circulation
        for door in doors:
            from_r = door.get("from_room")
            to_r = door.get("to_room")
            if from_r and to_r:
                graph[from_r].add(to_r)
                graph[to_r].add(from_r)

        # Corridors always act as physical pass-throughs: even if a toilet's
        # shared wall with the corridor is too narrow for a door, the corridor
        # still provides physical circulation access (the door opens inward into
        # the corridor space). Add geometric corridor-room edges unconditionally.
        if corridors and corridor_polygons:
            for corr_data, corr_poly in zip(corridors, corridor_polygons):
                corr_id = corr_data.get("id", "corridor_0")
                for rid in room_ids:
                    if polygons_share_boundary(
                        corr_poly, room_polygons[rid], min_length=0.1,
                    ):
                        graph[corr_id].add(rid)
                        graph[rid].add(corr_id)
    else:
        # Fallback to shared boundaries (pure geometry / pre-door tests)
        for i in range(len(room_ids)):
            for j in range(i + 1, len(room_ids)):
                id_a, id_b = room_ids[i], room_ids[j]
                if polygons_share_boundary(
                    room_polygons[id_a], room_polygons[id_b],
                    min_length=0.1,
                ):
                    graph[id_a].add(id_b)
                    graph[id_b].add(id_a)

        # Connect corridors to adjacent rooms if no doors
        if corridors and corridor_polygons:
            for corr_data, corr_poly in zip(corridors, corridor_polygons):
                corr_id = corr_data.get("id", "corridor_0")
                for rid in room_ids:
                    if polygons_share_boundary(
                        corr_poly, room_polygons[rid], min_length=0.1,
                    ):
                        graph[corr_id].add(rid)
                        graph[rid].add(corr_id)


    # Entrance (connect entrance room to a virtual "ENTRANCE" node)
    if entrance:
        ent_room = entrance.get("room_id")
        if ent_room and ent_room in graph:
            graph["ENTRANCE"].add(ent_room)
            graph[ent_room].add("ENTRANCE")

    return dict(graph)


def compute_shortest_paths(
    graph: Dict[str, Set[str]],
    start_node: str,
) -> Tuple[Dict[str, int], Dict[str, List[str]]]:
    """
    Compute shortest path hop distances and node paths from start_node using BFS.
    Ignores virtual 'ENTRANCE' node during traversal so paths remain inside the floor plan.

    Returns:
        (distances: {room_id: hops}, paths: {room_id: [start_node, ..., room_id]})
    """
    distances: Dict[str, int] = {start_node: 0}
    paths: Dict[str, List[str]] = {start_node: [start_node]}
    queue: deque = deque([start_node])

    while queue:
        curr = queue.popleft()
        curr_dist = distances[curr]
        curr_path = paths[curr]

        for neighbor in graph.get(curr, set()):
            if neighbor == "ENTRANCE":
                continue
            if neighbor not in distances:
                distances[neighbor] = curr_dist + 1
                paths[neighbor] = curr_path + [neighbor]
                queue.append(neighbor)

    return distances, paths


def compute_circulation_score(
    graph: Dict[str, Set[str]],
    room_ids: List[str],
    entrance_room_id: Optional[str] = None,
    room_types: Optional[Dict[str, str]] = None,
    corridors: Optional[List[dict]] = None,
) -> Tuple[float, Dict[str, float]]:
    """
    Compute weighted composite circulation score and breakdown:

      circulation_score = (
          0.30 * privacy_depth +
          0.25 * public_private_separation +
          0.20 * path_efficiency +
          0.15 * service_isolation +
          0.10 * corridor_presence
      )

    Returns:
        (circulation_score, circulation_breakdown)
    """
    if not room_ids:
        breakdown = {
            "privacy_depth": 1.0,
            "public_private_separation": 1.0,
            "path_efficiency": 1.0,
            "service_isolation": 1.0,
            "corridor_presence": 1.0,
        }
        return 1.0, breakdown

    # Determine start node for circulation analysis
    start_node = entrance_room_id if entrance_room_id and entrance_room_id in graph else (
        next(iter(graph["ENTRANCE"])) if "ENTRANCE" in graph and graph["ENTRANCE"] else (
            room_ids[0] if room_ids else None
        )
    )

    if not start_node or start_node not in graph:
        breakdown = {
            "privacy_depth": 0.0,
            "public_private_separation": 0.0,
            "path_efficiency": 0.0,
            "service_isolation": 0.0,
            "corridor_presence": 0.0,
        }
        return 0.0, breakdown

    distances, paths = compute_shortest_paths(graph, start_node)

    # Helper to resolve room type
    def get_rtype(rid: str) -> str:
        if room_types and rid in room_types:
            return (room_types[rid] or "").lower()
        base = rid.rsplit("_", 1)[0].lower()
        return base if base in ZONE_MAP else rid.lower()

    # ── 1. privacy_depth (0.30) ───────────────────────────────────────────
    # Fraction of private rooms (bedroom, master_bedroom, toilet attached to bedroom)
    # whose shortest path from entrance does NOT pass through another bedroom or kitchen.
    private_rooms: Set[str] = set()
    attached_toilets: Dict[str, str] = {}  # toilet_id -> parent_bedroom_id

    for rid in room_ids:
        rtype = get_rtype(rid)
        zone = ZONE_MAP.get(rtype, "")
        if zone == "private" or rtype in ("bedroom", "master_bedroom", "study", "dressing"):
            private_rooms.add(rid)
        elif rtype in ("toilet", "bathroom"):
            # Check if attached to a bedroom (only door neighbors are bedroom(s))
            neighbors = graph.get(rid, set()) - {"ENTRANCE"}
            if neighbors:
                is_attached = True
                parent_bed = None
                for n in neighbors:
                    ntype = get_rtype(n)
                    if ntype in ("bedroom", "master_bedroom"):
                        parent_bed = n
                    else:
                        is_attached = False
                        break
                if is_attached and parent_bed:
                    private_rooms.add(rid)
                    attached_toilets[rid] = parent_bed

    if not private_rooms:
        privacy_depth = 1.0
    else:
        satisfied = 0
        for prid in private_rooms:
            if prid not in paths:
                continue
            path = paths[prid]
            inter = path[1:-1]
            parent_bed = attached_toilets.get(prid)
            violates = False
            for node in inter:
                if parent_bed and node == parent_bed:
                    continue  # Accessing ensuite toilet through its parent bedroom is expected
                ntype = get_rtype(node)
                if ntype in ("bedroom", "master_bedroom", "kitchen"):
                    violates = True
                    break
            if not violates:
                satisfied += 1

        privacy_depth = satisfied / len(private_rooms)

    # ── 2. public_private_separation (0.25) ───────────────────────────────
    # Mean distance (in door hops) from entrance to private rooms minus mean
    # distance from entrance to public rooms (living, dining, foyer).
    # Normalized: hops_diff >= 1.0 -> 1.0; hops_diff <= 0.0 -> 0.2; linear between.
    public_rooms = set()
    for rid in room_ids:
        rtype = get_rtype(rid)
        if ZONE_MAP.get(rtype) == "public" or rtype in ("living", "dining", "foyer", "lobby"):
            public_rooms.add(rid)

    reachable_private = [r for r in private_rooms if r in distances]
    reachable_public = [r for r in public_rooms if r in distances]

    if not reachable_private or not reachable_public:
        public_private_separation = 1.0
    else:
        mean_priv = sum(distances[r] for r in reachable_private) / len(reachable_private)
        mean_pub = sum(distances[r] for r in reachable_public) / len(reachable_public)
        hops_diff = mean_priv - mean_pub

        if hops_diff >= 1.0:
            public_private_separation = 1.0
        elif hops_diff <= 0.0:
            public_private_separation = 0.2
        else:
            public_private_separation = 0.2 + 0.8 * hops_diff

    # ── 3. path_efficiency (0.20) ─────────────────────────────────────────
    # Mean shortest-path hops from entrance to all reachable rooms.
    # Score: 1.0 if mean <= 2.5 hops, decaying to 0.0 at >= 5.0 hops.
    reachable_rooms_list = [r for r in room_ids if r in distances]

    if not reachable_rooms_list:
        path_efficiency = 1.0 if len(room_ids) == 0 else 0.0
    else:
        mean_hops = sum(distances[r] for r in reachable_rooms_list) / len(reachable_rooms_list)
        if mean_hops <= 2.5:
            path_efficiency = 1.0
        elif mean_hops >= 5.0:
            path_efficiency = 0.0
        else:
            path_efficiency = 1.0 - (mean_hops - 2.5) / 2.5
        path_efficiency = max(0.0, min(1.0, path_efficiency))

    # ── 4. service_isolation (0.15) ───────────────────────────────────────
    # Kitchen and toilets do NOT lie on the shortest path between entrance and
    # any bedroom.
    # Score: 1.0 if zero violations; subtract 0.35 per violation down to 0.0.
    bedrooms = [r for r in room_ids if get_rtype(r) in ("bedroom", "master_bedroom")]

    service_violations = 0
    for b in bedrooms:
        if b not in paths:
            continue
        path = paths[b]
        inter = path[1:-1]
        for node in inter:
            ntype = get_rtype(node)
            if ntype in ("kitchen", "toilet", "bathroom"):
                service_violations += 1
                break

    service_isolation = max(0.0, 1.0 - 0.35 * service_violations)

    # ── 5. corridor_presence (0.10) ───────────────────────────────────────
    # If room count >= 6 and private room count >= 3:
    #   corridor present and connected: 1.0
    #   corridor absent: capped at 0.4
    # Else (small apartment, <6 rooms): 1.0
    has_corr = False
    for node in graph:
        ntype = get_rtype(node)
        if ntype == "corridor" or "corridor" in node.lower():
            if node in distances:
                has_corr = True
                break
    if corridors and not has_corr:
        for corr in corridors:
            cid = corr.get("id")
            if cid and cid in distances:
                has_corr = True
                break

    if len(room_ids) >= 6 and len(private_rooms) >= 3:
        corridor_presence = 1.0 if has_corr else 0.4
    else:
        corridor_presence = 1.0

    breakdown = {
        "privacy_depth": round(privacy_depth, 4),
        "public_private_separation": round(public_private_separation, 4),
        "path_efficiency": round(path_efficiency, 4),
        "service_isolation": round(service_isolation, 4),
        "corridor_presence": round(corridor_presence, 4),
    }

    raw_score = (
        0.30 * privacy_depth +
        0.25 * public_private_separation +
        0.20 * path_efficiency +
        0.15 * service_isolation +
        0.10 * corridor_presence
    )
    score = round(max(0.0, min(1.0, raw_score)), 4)

    return score, breakdown


def analyze_circulation(
    graph: Dict[str, Set[str]],
    room_ids: List[str],
    entrance_room_id: Optional[str] = None,
    room_types: Optional[Dict[str, str]] = None,
    corridors: Optional[List[dict]] = None,
) -> dict:
    """
    Analyze circulation connectivity and quality score.

    Determines:
    - Whether all non-parking rooms are reachable from the entrance via the door graph
    - Dead-end room count
    - Graph edges
    - Detailed composite circulation score and 5-metric breakdown

    Returns:
        Circulation analysis dict
    """
    total_rooms = len(room_ids)

    if total_rooms == 0:
        empty_breakdown = {
            "privacy_depth": 1.0,
            "public_private_separation": 1.0,
            "path_efficiency": 1.0,
            "service_isolation": 1.0,
            "corridor_presence": 1.0,
        }
        return {
            "connected": True,
            "reachable_rooms": 0,
            "total_rooms": 0,
            "dead_ends": 0,
            "graph_edges": 0,
            "score": 1.0,
            "breakdown": empty_breakdown,
            "circulation_breakdown": empty_breakdown,
        }

    # BFS from entrance or from first room
    start = entrance_room_id if entrance_room_id and entrance_room_id in graph else (
        next(iter(graph["ENTRANCE"])) if "ENTRANCE" in graph and graph["ENTRANCE"] else (
            room_ids[0] if room_ids else None
        )
    )

    visited: Set[str] = set()
    if start and start in graph:
        queue: deque = deque([start])
        visited.add(start)

        while queue:
            node = queue.popleft()
            for neighbor in graph.get(node, set()):
                if neighbor == "ENTRANCE":
                    continue
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

    # Count graph edges (excluding virtual ENTRANCE connections)
    edge_count = sum(
        len(v - {"ENTRANCE"}) for k, v in graph.items() if k != "ENTRANCE"
    ) // 2

    # Connectivity check: parking is exempt from interior door reachability
    def is_parking(rid: str) -> bool:
        if room_types and rid in room_types:
            return (room_types[rid] or "").lower() == "parking"
        return rid.lower().startswith("parking") or rid == "parking"

    rooms_to_reach = [rid for rid in room_ids if not is_parking(rid)]
    connected = all(rid in visited for rid in rooms_to_reach) if rooms_to_reach else True

    # Compute composite score and breakdown
    score, breakdown = compute_circulation_score(
        graph, room_ids, entrance_room_id, room_types=room_types, corridors=corridors,
    )

    # Hard constraint: if door graph is disconnected, score must be 0.0
    if not connected:
        score = 0.0

    return {
        "connected": connected,
        "reachable_rooms": reachable,
        "total_rooms": total_rooms,
        "dead_ends": dead_ends,
        "graph_edges": edge_count,
        "score": round(score, 4),
        "breakdown": breakdown,
        "circulation_breakdown": breakdown,
    }

