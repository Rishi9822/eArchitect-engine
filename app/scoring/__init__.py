"""
Scoring package — layout quality evaluation.
"""
from .scorer import score_layout
from .adjacency import score_adjacency, compute_room_adjacency
from .metrics import (
    score_natural_light,
    score_ventilation,
    score_dead_space,
    score_parking_accessibility,
    score_constraint_compliance,
)
