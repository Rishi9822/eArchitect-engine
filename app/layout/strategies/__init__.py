"""
Strategy dispatcher — routes strategy names to their generation functions.

Each strategy module exposes a `generate()` function with signature:

    generate(inner_polygon, specs, rng, facing) -> dict

The returned dict is BSP-compatible:
    zone_polygons, room_leaves, dead_polygons, unplaced_rooms, corridors
"""
from __future__ import annotations

import logging
from typing import List, Dict, Optional
import random

from shapely.geometry import Polygon

from ...layout.bsp import RoomSpec

logger = logging.getLogger(__name__)


def dispatch_strategy(
    strategy: str,
    inner_polygon: Polygon,
    specs: List[RoomSpec],
    rng: random.Random,
    facing: str = "north",
) -> Dict:
    """
    Dispatch to the appropriate strategy generator.

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

    try:
        result = gen_func(inner_polygon, specs, rng, facing)
        result["strategy"] = strategy
        return result
    except Exception as exc:
        logger.warning(
            "Strategy '%s' failed (%s); falling back to open_plan", strategy, exc
        )
        result = open_plan.generate(inner_polygon, specs, rng, facing)
        result["strategy"] = "open_plan"
        return result
