"""
Multi-candidate layout generation.

Generates N candidate layouts using different architectural strategies,
validates/scores each one, deduplicates, and returns diverse candidates.
"""
from __future__ import annotations

import hashlib
import logging
import random
from typing import List, Dict, Optional

from shapely.geometry import Polygon

from ..config import (
    CANDIDATE_STRATEGIES,
    DEFAULT_CANDIDATE_COUNT,
    MAX_CANDIDATE_COUNT,
    INTERNAL_CANDIDATE_COUNT,
)
from ..layout.bsp import RoomSpec
from ..layout.strategies import dispatch_strategy

logger = logging.getLogger(__name__)


def _derive_seed(base_seed: int, strategy: str, index: int) -> int:
    """
    Derive a deterministic per-candidate seed.

    Uses a hash of (base_seed, strategy, index) for robust
    separation between candidates.
    """
    raw = f"{base_seed}:{strategy}:{index}".encode("utf-8")
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
    Generate multiple layout candidates using different strategies.

    Each candidate uses a different architectural strategy and a
    deterministically-derived seed to produce genuinely different layouts.

    Generates more candidates internally than requested, so the
    downstream pipeline can deduplicate and select diverse results.

    Args:
        inner_polygon:   buildable area polygon
        specs:           list of RoomSpec objects
        candidate_count: number of candidates requested by caller
        seed:            base random seed
        facing:          plot facing direction

    Returns:
        list of candidate dicts, each containing BSP results + strategy name
    """
    candidate_count = min(candidate_count, MAX_CANDIDATE_COUNT)
    base_seed = seed if seed is not None else 42

    # Generate more internally for diversity selection
    internal_count = max(candidate_count, min(INTERNAL_CANDIDATE_COUNT, len(CANDIDATE_STRATEGIES) * 2))

    candidates = []

    for i in range(internal_count):
        strategy = CANDIDATE_STRATEGIES[i % len(CANDIDATE_STRATEGIES)]
        candidate_seed = _derive_seed(base_seed, strategy, i)

        logger.info(
            "Generating candidate %d/%d (strategy=%s, seed=%d)",
            i + 1, internal_count, strategy, candidate_seed,
        )

        rng = random.Random(candidate_seed)

        try:
            result = dispatch_strategy(
                strategy=strategy,
                inner_polygon=inner_polygon,
                specs=specs,
                rng=rng,
                facing=facing,
            )

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
        fallback_rng = random.Random(base_seed)
        from ..layout.strategies.open_plan import generate as open_plan_gen
        result = open_plan_gen(inner_polygon, specs, fallback_rng, facing)
        result["strategy"] = "open_plan"
        result["seed"] = base_seed
        result["candidate_index"] = 0
        candidates.append(result)

    return candidates
