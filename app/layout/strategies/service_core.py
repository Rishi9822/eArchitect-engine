"""
Service Core strategy — cluster service rooms together.

Groups kitchen, toilet, and utility into a compact cluster,
then places public and private rooms around them.

Uses zone order: service → public → private → parking.
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
    Generate a layout with a clustered service core.

    Service rooms (kitchen, toilet, utility) are partitioned first,
    receiving a contiguous region. Public and private rooms fill
    the remainder.
    """
    seed = rng.randint(0, 2**31 - 1)

    # Service first to get a contiguous cluster
    zone_order = ["service", "public", "private", "parking"]

    result = generate_bsp_layout(
        inner_polygon=inner_polygon,
        specs=specs,
        seed=seed,
        zone_order_override=zone_order,
        split_jitter=0.06,
    )

    result["corridors"] = []
    return result
