"""
Open Plan strategy — minimal dedicated circulation.

Rooms connect directly where possible. No dedicated corridor
is generated. This strategy prioritises efficient usable area
and short circulation paths.

Supports geometric variations:
  - standard: default zone order (public → private → service → parking)
  - alternate_axis: alternate primary split axis with split jitter
  - service_first: zone order (service → public → private → parking)
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
    variation: str = "standard",
) -> Dict:
    """
    Generate an open-plan layout with no dedicated corridor.
    """
    seed = rng.randint(0, 2**31 - 1)

    if variation == "alternate_axis":
        result = generate_bsp_layout(
            inner_polygon=inner_polygon,
            specs=specs,
            seed=seed,
            zone_order_override=None,
            split_jitter=0.08,
            prefer_alternate_axis=True,
        )
    elif variation == "service_first":
        zone_order = ["service", "public", "private", "parking"]
        result = generate_bsp_layout(
            inner_polygon=inner_polygon,
            specs=specs,
            seed=seed,
            zone_order_override=zone_order,
            split_jitter=0.06,
        )
    else:  # standard / default
        result = generate_bsp_layout(
            inner_polygon=inner_polygon,
            specs=specs,
            seed=seed,
            zone_order_override=None,
            split_jitter=0.0,
        )

    result["corridors"] = []
    result["strategy"] = "open_plan"
    result["variation"] = variation
    return result
