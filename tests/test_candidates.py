"""
Tests for multi-candidate generation and ranking.
"""
import pytest
from shapely.geometry import Polygon
from app.layout.bsp import RoomSpec, build_room_specs
from app.optimization.candidates import generate_candidates
from app.optimization.ranking import rank_candidates
from app.config import SQ_FT_TO_SQ_M


class TestCandidates:
    def test_generate_multiple_candidates(self):
        poly = Polygon([(0, 0), (20, 0), (20, 15), (0, 15)])
        specs = build_room_specs([
            {"id": "living_0", "type": "living", "min_area_sqm": 150 * SQ_FT_TO_SQ_M, "priority": 10},
            {"id": "bedroom_0", "type": "bedroom", "min_area_sqm": 120 * SQ_FT_TO_SQ_M, "priority": 20},
            {"id": "kitchen_0", "type": "kitchen", "min_area_sqm": 80 * SQ_FT_TO_SQ_M, "priority": 30},
        ], {"parking": False})

        candidates = generate_candidates(poly, specs, candidate_count=3, seed=42)
        assert len(candidates) == 3
        strategies = [c["strategy"] for c in candidates]
        assert "balanced" in strategies
        assert "compact" in strategies
        assert "zoned" in strategies

    def test_ranking_orders_valid_first_then_score(self):
        candidates = [
            {"id": "c1", "strategy": "balanced", "validation": {"valid": False}, "score": {"overall": 0.95}},
            {"id": "c2", "strategy": "compact", "validation": {"valid": True}, "score": {"overall": 0.85}},
            {"id": "c3", "strategy": "zoned", "validation": {"valid": True}, "score": {"overall": 0.90}},
        ]

        ranked = rank_candidates(candidates)
        assert ranked[0]["id"] == "c3"  # Valid and highest score (0.90)
        assert ranked[1]["id"] == "c2"  # Valid with score 0.85
        assert ranked[2]["id"] == "c1"  # Invalid ranked last despite high raw score
        assert ranked[0]["rank"] == 1
        assert ranked[1]["rank"] == 2
        assert ranked[2]["rank"] == 3
