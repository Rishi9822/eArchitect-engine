"""
Strategy dispatcher — routes strategy and variation to generation functions.

Each strategy module exposes a `generate(inner_polygon, specs, rng, facing, variation)` function.

The returned dict is BSP-compatible:
    strategy, variation, zone_polygons, room_leaves, dead_polygons, unplaced_rooms, corridors
"""
from __future__ import annotations

import logging
from typing import List, Dict, Optional
import random

from shapely.geometry import Polygon

from ...layout.bsp import RoomSpec, BSPNode
from ..parking import place_fixed_parking

logger = logging.getLogger(__name__)


def dispatch_strategy(
    strategy: str,
    inner_polygon: Polygon,
    specs: List[RoomSpec],
    rng: random.Random,
    facing: str = "north",
    variation: Optional[str] = None,
    road_side: str = "front",
) -> Dict:
    """
    Dispatch to the appropriate strategy generator with the specified variation.

    Priority 8:
    If a parking room is present in specs, carve a fixed-footprint parking space
    (2.5m x 5.0m clear per car + 0.5m margin = 3.0m x 5.5m) directly along the road-side
    boundary BEFORE strategy/BSP partitioning, returning leftover area to the BSP pool.

    Falls back to open_plan if the requested strategy fails.
    """
    from . import (
        open_plan,
        central_corridor,
        side_corridor,
        public_private,
        service_core,
        compact,
    )

    strategy_map = {
        "open_plan": open_plan.generate,
        "central_corridor": central_corridor.generate,
        "side_corridor": side_corridor.generate,
        "public_private": public_private.generate,
        "service_core": service_core.generate,
        "compact": compact.generate,
    }

    gen_func = strategy_map.get(strategy)
    if gen_func is None:
        logger.warning("Unknown strategy '%s'; falling back to open_plan", strategy)
        gen_func = open_plan.generate
        strategy = "open_plan"

    parking_spec = next((s for s in specs if s.type == "parking"), None)
    parking_poly = None
    target_polygon = inner_polygon
    active_specs = specs

    if parking_spec is not None:
        carved_poly, house_poly = place_fixed_parking(
            inner_polygon=inner_polygon,
            road_side=road_side,
            facing=facing,
            rng=rng,
        )
        if carved_poly is not None:
            parking_poly = carved_poly
            target_polygon = house_poly
            active_specs = [s for s in specs if s.type != "parking"]

    try:
        if variation is not None:
            result = gen_func(target_polygon, active_specs, rng, facing, variation=variation)
        else:
            result = gen_func(target_polygon, active_specs, rng, facing)

        result["strategy"] = strategy
        if "variation" not in result:
            result["variation"] = variation or "default"
    except Exception as exc:
        logger.warning(
            "Strategy '%s' (var=%s) failed (%s); falling back to open_plan",
            strategy, variation, exc,
        )
        result = open_plan.generate(target_polygon, active_specs, rng, facing)
        result["strategy"] = "open_plan"
        result["variation"] = "fallback"

    # Attach carved fixed parking entity if applicable
    if parking_spec is not None and parking_poly is not None:
        result.setdefault("room_leaves", {})[parking_spec.id] = BSPNode(
            polygon=parking_poly,
            room=parking_spec,
        )
        result.setdefault("zone_polygons", {})["parking"] = parking_poly

    return result
