"""
Public/Private strategy — enforce zone separation.

Forces an explicit boundary between:
  - public rooms (living, dining, foyer)
  - private rooms (bedrooms, study)
  - service rooms (kitchen, toilet, utility)

Uses reversed zone order (private first) and a different split
axis preference to produce a layout that differs from open_plan.
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
    Generate a layout with enforced public/private separation.

    Uses reversed zone order so private rooms are partitioned first
    (getting a different region), then public, then service.
    """
    seed = rng.randint(0, 2**31 - 1)

    # Reverse zone order: private first, then public, then service
    zone_order = ["private", "public", "service", "parking"]

    result = generate_bsp_layout(
        inner_polygon=inner_polygon,
        specs=specs,
        seed=seed,
        zone_order_override=zone_order,
        split_jitter=0.08,
    )

    result["corridors"] = []
    return result
