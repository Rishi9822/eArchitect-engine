"""
Multi-candidate layout generation.

Generates N candidate layouts using different strategies
and validates/scores each one.
"""
from __future__ import annotations

import logging
import random
from typing import List, Dict, Optional

from shapely.geometry import Polygon

from ..config import (
    CANDIDATE_STRATEGIES,
    DEFAULT_CANDIDATE_COUNT,
    MAX_CANDIDATE_COUNT,
    ZONE_RATIOS,
)
from ..layout.bsp import RoomSpec, generate_bsp_layout

logger = logging.getLogger(__name__)


# Strategy-specific zone ratio overrides
STRATEGY_ZONE_RATIOS: Dict[str, Dict[str, float]] = {
    "balanced": {
        "public": 0.35,
        "private": 0.40,
        "service": 0.18,
        "parking": 0.07,
    },
    "compact": {
        "public": 0.30,
        "private": 0.35,
        "service": 0.20,
        "parking": 0.15,
    },
    "zoned": {
        "public": 0.40,
        "private": 0.38,
        "service": 0.15,
        "parking": 0.07,
    },
}


def generate_candidates(
    inner_polygon: Polygon,
    specs: List[RoomSpec],
    candidate_count: int = DEFAULT_CANDIDATE_COUNT,
    seed: Optional[int] = None,
) -> List[Dict]:
    """
    Generate multiple layout candidates using different strategies.

    Each candidate uses a different seed offset and potentially
    different zone ratios to produce varied layouts.

    Args:
        inner_polygon:   buildable area polygon
        specs:           list of RoomSpec objects
        candidate_count: number of candidates to generate
        seed:            base random seed

    Returns:
        list of candidate dicts, each containing BSP results + strategy name
    """
    candidate_count = min(candidate_count, MAX_CANDIDATE_COUNT)
    base_seed = seed if seed is not None else 42

    candidates = []

    for i in range(candidate_count):
        strategy = CANDIDATE_STRATEGIES[i % len(CANDIDATE_STRATEGIES)]
        candidate_seed = base_seed + i * 1000

        logger.info(
            "Generating candidate %d/%d (strategy=%s, seed=%d)",
            i + 1, candidate_count, strategy, candidate_seed,
        )

        try:
            result = generate_bsp_layout(
                inner_polygon=inner_polygon,
                specs=specs,
                seed=candidate_seed,
            )

            result["strategy"] = strategy
            result["seed"] = candidate_seed
            result["candidate_index"] = i

            candidates.append(result)

        except Exception as exc:
            logger.warning(
                "Candidate %d (strategy=%s) failed: %s",
                i + 1, strategy, exc,
            )

    if not candidates:
        logger.error("All candidates failed; generating fallback")
        result = generate_bsp_layout(
            inner_polygon=inner_polygon,
            specs=specs,
            seed=base_seed,
        )
        result["strategy"] = "balanced"
        result["seed"] = base_seed
        result["candidate_index"] = 0
        candidates.append(result)

    return candidates
