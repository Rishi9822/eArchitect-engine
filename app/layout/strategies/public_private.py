"""
Public/Private strategy — enforce zone separation.

Forces an explicit boundary between:
  - public rooms (living, dining, foyer)
  - private rooms (bedrooms, study)
  - service rooms (kitchen, toilet, utility)

Supports geometric variations:
  - left_private: private rooms placed on the left side (X-split, part_a)
  - right_private: private rooms placed on the right side (X-split, part_b)
  - reversed: private partitioned first in rear (Y-split, reversed order)
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
    variation: str = "left_private",
) -> Dict:
    """
    Generate a layout with enforced public/private separation.
    """
    seed = rng.randint(0, 2**31 - 1)

    if variation == "right_private":
        zone_order = ["private", "public", "service", "parking"]
        result = generate_bsp_layout(
            inner_polygon=inner_polygon,
            specs=specs,
            seed=seed,
            zone_order_override=zone_order,
            split_jitter=0.06,
            forced_axis="x",
            flip_sides=True,
        )
    elif variation == "reversed":
        zone_order = ["private", "public", "service", "parking"]
        result = generate_bsp_layout(
            inner_polygon=inner_polygon,
            specs=specs,
            seed=seed,
            zone_order_override=zone_order,
            split_jitter=0.08,
            forced_axis="y",
            flip_sides=True,
        )
    else:  # left_private / default
        zone_order = ["private", "public", "service", "parking"]
        result = generate_bsp_layout(
            inner_polygon=inner_polygon,
            specs=specs,
            seed=seed,
            zone_order_override=zone_order,
            split_jitter=0.06,
            forced_axis="x",
            flip_sides=False,
        )

    result["corridors"] = []
    result["strategy"] = "public_private"
    result["variation"] = variation
    return result
