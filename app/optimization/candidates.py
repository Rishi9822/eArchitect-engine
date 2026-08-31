"""
Multi-candidate layout generation.

Generates candidate layouts using diverse architectural strategies and variations,
validates/scores each one, deduplicates geometrically, and returns top distinct candidates.
"""
from __future__ import annotations

import hashlib
import logging
import random
import secrets
from typing import List, Dict, Optional

from shapely.geometry import Polygon

from ..config import (
    CANDIDATE_STRATEGY_VARIATION_PAIRS,
    DEFAULT_CANDIDATE_COUNT,
    MAX_CANDIDATE_COUNT,
    INTERNAL_CANDIDATE_COUNT,
)
from ..layout.bsp import RoomSpec
from ..layout.strategies import dispatch_strategy

logger = logging.getLogger(__name__)


def _derive_seed(base_seed: int, strategy: str, variation: str, index: int) -> int:
    """
    Derive a deterministic per-candidate seed from base_seed, strategy, variation, and index.
    """
    raw = f"{base_seed}:{strategy}:{variation}:{index}".encode("utf-8")
    h = hashlib.sha256(raw).digest()
    return int.from_bytes(h[:4], "big")


def generate_candidates(
    inner_polygon: Polygon,
    specs: List[RoomSpec],
    candidate_count: int = DEFAULT_CANDIDATE_COUNT,
    seed: Optional[int] = None,
    facing: str = "north",
) -> List[Dict]:
    """
    Generate an internal pool of layout candidates using diverse strategy-variation pairs.

    - When `seed` is provided, execution is 100% deterministic.
    - When `seed` is None, a dynamic base seed is generated for controlled run-to-run diversity.
    - Internally over-generates candidates across multiple strategies and geometric variations.

    Args:
        inner_polygon:   buildable area polygon
        specs:           list of RoomSpec objects
        candidate_count: number of candidates requested by caller
        seed:            base random seed (optional)
        facing:          plot facing direction

    Returns:
        list of candidate dicts with BSP results, strategy, and variation
    """
    candidate_count = max(1, min(candidate_count, MAX_CANDIDATE_COUNT))

    if seed is not None:
        base_seed = seed
    else:
        # Controlled run-to-run randomness
        base_seed = random.randint(1, 1_000_000_000)

    # Determine internal pool size (at least candidate_count * 3, up to total pairs)
    total_pairs = len(CANDIDATE_STRATEGY_VARIATION_PAIRS)
    internal_count = min(total_pairs, max(candidate_count * 3, INTERNAL_CANDIDATE_COUNT))

    candidates = []

    for i in range(internal_count):
        strategy, variation = CANDIDATE_STRATEGY_VARIATION_PAIRS[i % total_pairs]
        candidate_seed = _derive_seed(base_seed, strategy, variation, i)

        logger.info(
            "Generating candidate %d/%d (strategy=%s, variation=%s, seed=%d)",
            i + 1, internal_count, strategy, variation, candidate_seed,
        )

        rng = random.Random(candidate_seed)

        try:
            result = dispatch_strategy(
                strategy=strategy,
                inner_polygon=inner_polygon,
                specs=specs,
                rng=rng,
                facing=facing,
                variation=variation,
            )

            result["seed"] = candidate_seed
            result["candidate_index"] = i
            result["strategy"] = strategy
            result["variation"] = variation

            candidates.append(result)

        except Exception as exc:
            logger.warning(
                "Candidate %d (strategy=%s, var=%s) failed: %s",
                i + 1, strategy, variation, exc,
            )

    if not candidates:
        logger.error("All candidates failed; generating fallback")
        fallback_rng = random.Random(base_seed)
        from ..layout.strategies.open_plan import generate as open_plan_gen
        result = open_plan_gen(inner_polygon, specs, fallback_rng, facing)
        result["strategy"] = "open_plan"
        result["variation"] = "standard"
        result["seed"] = base_seed
        result["candidate_index"] = 0
        candidates.append(result)

    return candidates
