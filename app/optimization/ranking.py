"""
Candidate ranking — sorts candidates by overall score
and identifies the best one.
"""
from __future__ import annotations

import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


def rank_candidates(
    candidates: List[Dict],
) -> List[Dict]:
    """
    Rank candidate layouts by overall score (descending).

    Invalid candidates (validation.valid == False) are ranked
    below valid ones regardless of score.

    Returns:
        Sorted list of candidates (best first)
    """
    def sort_key(c: Dict):
        is_valid = c.get("validation", {}).get("valid", True)
        score = c.get("score", {}).get("overall", 0.0)
        # Valid candidates ranked first, then by score descending
        return (-int(is_valid), -score)

    ranked = sorted(candidates, key=sort_key)

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
