"""
Compact strategy — minimise dead space and wasted circulation.

Uses a different split axis preference (alternating) and tighter
split ratios to produce a more densely packed layout.

This differs from open_plan by:
  - Using the alternate axis for the primary split
  - Applying split jitter for variation
  - Using a tighter zone order (parking merged early)
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
    Generate a compact layout that minimises wasted space.

    Uses alternate split axis preference and jitter to produce
    a layout distinct from open_plan.
    """
    seed = rng.randint(0, 2**31 - 1)

    # Group parking with service early; public last (gets remainder)
    zone_order = ["parking", "service", "private", "public"]

    result = generate_bsp_layout(
        inner_polygon=inner_polygon,
        specs=specs,
        seed=seed,
        zone_order_override=zone_order,
        split_jitter=0.10,
        prefer_alternate_axis=True,
    )

    result["corridors"] = []
    return result
