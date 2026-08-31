"""
Service Core strategy — cluster service rooms together.

Groups kitchen, toilet, and utility into a compact cluster,
then places public and private rooms around them.

Supports geometric variations:
  - left_core: service cluster placed on the left flank
  - right_core: service cluster placed on the right flank
  - central_core: service cluster placed centrally with surrounding public/private
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
    variation: str = "left_core",
) -> Dict:
    """
    Generate a layout with a clustered service core.
    """
    seed = rng.randint(0, 2**31 - 1)

    zone_order = ["service", "public", "private", "parking"]

    if variation == "right_core":
        result = generate_bsp_layout(
            inner_polygon=inner_polygon,
            specs=specs,
            seed=seed,
            zone_order_override=zone_order,
            split_jitter=0.06,
            forced_axis="x",
            flip_sides=True,
        )
    elif variation == "central_core":
        result = generate_bsp_layout(
            inner_polygon=inner_polygon,
            specs=specs,
            seed=seed,
            zone_order_override=zone_order,
            split_jitter=0.08,
            forced_axis="y",
            flip_sides=False,
        )
    else:  # left_core / default
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
    result["strategy"] = "service_core"
    result["variation"] = variation
    return result
