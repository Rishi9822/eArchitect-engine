"""
Central Corridor strategy — explicit central circulation corridor.

Carves a corridor strip through the centre of the buildable area,
then runs BSP on the two remaining regions. Public rooms are placed
on the entrance side; private rooms on the far side.
"""
from __future__ import annotations

import random
from typing import List, Dict

from shapely.geometry import Polygon
from shapely.ops import unary_union

from ...config import ZONE_MAP, ZONE_ORDER, MIN_POLYGON_AREA_SQM
from ...layout.bsp import (
    RoomSpec,
    BSPNode,
    zone_partition,
    recursive_bsp,
    collect_leaves,
)
from ...layout.corridor import generate_central_corridor, build_corridor_data


def generate(
    inner_polygon: Polygon,
    specs: List[RoomSpec],
    rng: random.Random,
    facing: str = "north",
) -> Dict:
    """
    Generate a layout with a central corridor.

    Steps:
    1. Carve central corridor from buildable area
    2. Split specs into entrance-side (public+service) and far-side (private)
    3. Run BSP on each region independently
    4. Combine results
    """
    corridor_poly, region_a, region_b = generate_central_corridor(
        inner_polygon, facing, rng,
    )

    if corridor_poly is None:
        # Fallback: generate without corridor
        from .open_plan import generate as open_plan_gen
        result = open_plan_gen(inner_polygon, specs, rng, facing)
        result["strategy"] = "central_corridor"
        return result

    # Classify rooms by zone for region assignment
    public_service = [s for s in specs if s.zone in ("public", "service", "parking")]
    private = [s for s in specs if s.zone == "private"]

    # If no clear split, just divide evenly
    if not public_service:
        public_service = specs[:len(specs) // 2]
        private = specs[len(specs) // 2:]
    elif not private:
        private = []

    # Assign larger region to the group with more area need
    pub_area = sum(s.min_area_sqm for s in public_service)
    priv_area = sum(s.min_area_sqm for s in private)

    if region_a.area >= region_b.area:
        large_region, small_region = region_a, region_b
    else:
        large_region, small_region = region_b, region_a

    if pub_area >= priv_area:
        pub_region, priv_region = large_region, small_region
    else:
        pub_region, priv_region = small_region, large_region

    # BSP each region
    room_leaves: Dict[str, BSPNode] = {}
    zone_polygons: Dict[str, Polygon] = {}
    zone_used: List[Polygon] = []

    seed_a = rng.randint(0, 2**31 - 1)
    seed_b = rng.randint(0, 2**31 - 1)

    for region, room_specs, region_seed in [
        (pub_region, public_service, seed_a),
        (priv_region, private, seed_b),
    ]:
        if not room_specs or region is None:
            continue

        region_rng = random.Random(region_seed)

        # Group by zone
        rooms_by_zone: Dict[str, List[RoomSpec]] = {}
        for s in room_specs:
            rooms_by_zone.setdefault(s.zone, []).append(s)

        zp = zone_partition(region, rooms_by_zone)
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

    # Unplaced rooms
    placed_ids = set(room_leaves.keys())
    unplaced = [s for s in specs if s.id not in placed_ids]

    # Build corridor data (connected_rooms will be computed later in service)
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
