"""
Candidate ranking — sorts candidates by overall score,
removes duplicates, and selects diverse high-quality results.
"""
from __future__ import annotations

import logging
from typing import List, Dict, Optional

from .diversity import select_diverse_candidates
from .fingerprint import deduplicate_candidates

logger = logging.getLogger(__name__)


def rank_candidates(
    candidates: List[Dict],
    target_count: Optional[int] = None,
) -> List[Dict]:
    """
    Rank candidate layouts by overall score (descending).

    Pipeline:
    1. Sort by validity then score
    2. Remove geometric duplicates
    3. Select diverse subset (if target_count specified)
    4. Assign final ranks

    Invalid candidates (validation.valid == False) are ranked
    below valid ones regardless of score.

    Args:
        candidates:    list of processed candidate dicts
        target_count:  if set, return at most this many diverse candidates

    Returns:
        Sorted list of candidates (best first)
    """
    def sort_key(c: Dict):
        is_valid = c.get("validation", {}).get("valid", True)
        score = c.get("score", {}).get("overall", 0.0)
        # Valid candidates ranked first, then by score descending
        return (-int(is_valid), -score)

    ranked = sorted(candidates, key=sort_key)

    # Deduplicate
    ranked = deduplicate_candidates(ranked)

    # Diversity selection
    if target_count is not None and len(ranked) > target_count:
        ranked = select_diverse_candidates(ranked, target_count=target_count)
        # Re-sort after diversity selection
        ranked = sorted(ranked, key=sort_key)

    for i, c in enumerate(ranked):
        c["rank"] = i + 1

    if ranked:
        logger.info(
            "Ranked %d candidates. Best: strategy=%s, score=%.4f",
            len(ranked),
            ranked[0].get("strategy", "unknown"),
            ranked[0].get("score", {}).get("overall", 0),
        )

    return ranked


def select_best(candidates: List[Dict]) -> Optional[str]:
    """Return the ID of the best candidate, or None."""
    if not candidates:
        return None
    ranked = rank_candidates(candidates)
    return ranked[0].get("id")
