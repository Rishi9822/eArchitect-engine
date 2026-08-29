"""
Open Plan strategy — minimal dedicated circulation.

Rooms connect directly where possible. No dedicated corridor
is generated. This strategy prioritises efficient usable area
and short circulation paths.

Uses the standard BSP zone partition with the default zone order
(public → private → service → parking).
"""
from __future__ import annotations

import random
from typing import List, Dict

from shapely.geometry import Polygon

from ...layout.bsp import RoomSpec, generate_bsp_layout


def generate(
    inner_polygon: Polygon,
    specs: List[RoomSpec],
    rng: random.Random,
    facing: str = "north",
) -> Dict:
    """
    Generate an open-plan layout with no dedicated corridor.

    Uses the standard BSP with the default zone order.
    Seed is derived from rng for determinism.
    """
    seed = rng.randint(0, 2**31 - 1)

    result = generate_bsp_layout(
        inner_polygon=inner_polygon,
        specs=specs,
        seed=seed,
        zone_order_override=None,
        split_jitter=0.0,
    )

    result["corridors"] = []
    return result
