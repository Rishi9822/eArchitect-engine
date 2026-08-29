"""
Side Corridor strategy — dedicated corridor along one side.

All rooms are accessed from a corridor running along one edge
of the buildable area.
"""
from __future__ import annotations

import random
from typing import List, Dict

from shapely.geometry import Polygon
from shapely.ops import unary_union

from ...config import ZONE_MAP, MIN_POLYGON_AREA_SQM
from ...layout.bsp import (
    RoomSpec,
    BSPNode,
    zone_partition,
    recursive_bsp,
    collect_leaves,
)
from ...layout.corridor import generate_side_corridor, build_corridor_data


def generate(
    inner_polygon: Polygon,
    specs: List[RoomSpec],
    rng: random.Random,
    facing: str = "north",
) -> Dict:
    """
    Generate a layout with a side corridor.

    Steps:
    1. Carve corridor along one side
    2. Run full BSP on the remaining region
    """
    corridor_poly, main_region, _ = generate_side_corridor(
        inner_polygon, facing, rng,
    )

    if corridor_poly is None or main_region is None:
        from .open_plan import generate as open_plan_gen
        result = open_plan_gen(inner_polygon, specs, rng, facing)
        result["strategy"] = "side_corridor"
        return result

    # BSP on the main region
    room_leaves: Dict[str, BSPNode] = {}
    zone_polygons: Dict[str, Polygon] = {}
    zone_used: List[Polygon] = []

    seed_val = rng.randint(0, 2**31 - 1)
    region_rng = random.Random(seed_val)

    rooms_by_zone: Dict[str, List[RoomSpec]] = {}
    for s in specs:
        rooms_by_zone.setdefault(s.zone, []).append(s)

    zp = zone_partition(main_region, rooms_by_zone)
    zone_polygons.update(zp)

    for zone, zone_poly in zp.items():
        zone_rooms = rooms_by_zone.get(zone, [])
        if not zone_rooms:
            continue
        root = recursive_bsp(zone_poly, zone_rooms, depth=0, rng=region_rng)
        leaves = collect_leaves(root)
        for leaf in leaves:
            if leaf.room is not None:
                room_leaves[leaf.room.id] = leaf
                zone_used.append(leaf.polygon)

    # Dead spaces
    used_union = unary_union(zone_used + [corridor_poly]) if zone_used else corridor_poly
    leftover = inner_polygon.difference(used_union)
    dead_polygons: List[Polygon] = []
    if not leftover.is_empty:
        geoms = list(leftover.geoms) if hasattr(leftover, "geoms") else [leftover]
        for g in geoms:
            if isinstance(g, Polygon) and g.area >= 0.5:
                dead_polygons.append(g)

    placed_ids = set(room_leaves.keys())
    unplaced = [s for s in specs if s.id not in placed_ids]

    room_polys = {rid: leaf.polygon for rid, leaf in room_leaves.items() if leaf.room}
    corridor_data = build_corridor_data(corridor_poly, room_polys)

    return {
        "zone_polygons": zone_polygons,
        "room_leaves": room_leaves,
        "dead_polygons": dead_polygons,
        "unplaced_rooms": unplaced,
        "corridors": [corridor_data],
        "corridor_polygons": [corridor_poly],
    }
