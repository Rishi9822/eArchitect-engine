"""
Optimization package — candidate generation, ranking, fingerprinting, and diversity.
"""
from .candidates import generate_candidates
from .ranking import rank_candidates, select_best
from .fingerprint import layout_fingerprint, deduplicate_candidates
from .diversity import select_diverse_candidates, pairwise_diversity
