"""
Compact strategy — minimise dead space and wasted circulation.

Supports geometric variations:
  - dense_front: groups parking and service in front, private and public behind
  - dense_corner: uses alternate split axis and higher jitter to pack rooms tightly
"""
from __future__ import annotations

import random
from typing import List, Dict, Optional

from shapely.geometry import Polygon

from ...layout.bsp import RoomSpec, generate_bsp_layout


def generate(
    inner_polygon: Polygon,
    specs: List[RoomSpec],
    rng: random.Random,
    facing: str = "north",
    variation: str = "dense_front",
) -> Dict:
    """
    Generate a compact layout that minimises wasted space.
    """
    seed = rng.randint(0, 2**31 - 1)

    if variation == "dense_corner":
        zone_order = ["parking", "service", "public", "private"]
        result = generate_bsp_layout(
            inner_polygon=inner_polygon,
            specs=specs,
            seed=seed,
            zone_order_override=zone_order,
            split_jitter=0.12,
            prefer_alternate_axis=True,
        )
    else:  # dense_front / default
        zone_order = ["parking", "service", "private", "public"]
        result = generate_bsp_layout(
            inner_polygon=inner_polygon,
            specs=specs,
            seed=seed,
            zone_order_override=zone_order,
            split_jitter=0.08,
            prefer_alternate_axis=False,
        )

    result["corridors"] = []
    result["strategy"] = "compact"
    result["variation"] = variation
    return result
