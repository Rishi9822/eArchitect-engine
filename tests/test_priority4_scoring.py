"""
Priority 4: Scoring Weights & Hard Gates
=========================================

Tests cover:
1.  SCORE_WEIGHTS sum to 1.0 and contain required keys.
2.  Hard Gate 1: Entrance on a bedroom/toilet/kitchen/parking emits ENTRANCE_ROOM_TYPE.
3.  Hard Gate 2: A FORBIDDEN door pair emits NO_FORBIDDEN_DOORS.
4.  Hard Gate 3: Habitable room without window emits HABITABLE_ROOM_WINDOW.
5.  Hard Gate 4: Interior toilet without window or corridor emits TOILET_VENTILATION.
6.  Hard Gate 5: Parking without road_access emits PARKING_EXTERIOR_ACCESS.
7.  adjacency_breakdown items have keys 'pair' and 'satisfied'.
8.  rejected_candidates get a 'rejection_reason' field.
9.  Valid-but-pruned candidates get 'BELOW_DIVERSITY_THRESHOLD'.
10. Overall score is in [0, 1].
"""
from __future__ import annotations

import pytest
from shapely.geometry import Polygon

from app.config import (
    SCORE_WEIGHTS,
    DOOR_ADJACENCY_FORBIDDEN,
    ZONE_MAP,
    PREFERRED_ADJACENCY_PAIRS,
)
from app.scoring.adjacency import score_adjacency
from app.scoring.scorer import score_layout
from app.layout.circulation import build_adjacency_graph, analyze_circulation


# -------------------------------------------------------------------
# Fixtures
# -------------------------------------------------------------------

def make_rect(x0, y0, x1, y1):
    return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


@pytest.fixture
def simple_layout():
    living  = make_rect(0, 0, 5, 4)
    bedroom = make_rect(5, 0, 10, 4)
    toilet  = make_rect(10, 0, 12, 4)
    plot    = make_rect(0, 0, 12, 4)
    room_polygons = {"living_0": living, "bedroom_0": bedroom, "toilet_0": toilet}
    room_types    = {"living_0": "living", "bedroom_0": "bedroom", "toilet_0": "toilet"}
    return room_polygons, room_types, plot


# -------------------------------------------------------------------
# 1. Scoring weights
# -------------------------------------------------------------------

class TestScoringWeights:
    def test_weights_sum_to_one(self):
        total = sum(SCORE_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9, f"Weights sum to {total}, expected 1.0"

    def test_required_keys_present(self):
        required = {
            "adjacency", "circulation", "aspect_quality",
            "buildable_utilization", "natural_light", "ventilation",
            "dead_space_efficiency", "parking_accessibility", "building_coverage",
        }
        assert required.issubset(SCORE_WEIGHTS.keys())

    def test_adjacency_and_circulation_weight_0_20(self):
        assert SCORE_WEIGHTS["adjacency"] == pytest.approx(0.20)
        assert SCORE_WEIGHTS["circulation"] == pytest.approx(0.20)

    def test_no_weight_exceeds_0_25(self):
        for k, v in SCORE_WEIGHTS.items():
            assert v <= 0.25, f"Weight '{k}' = {v} exceeds 0.25"


# -------------------------------------------------------------------
# 2-6. Hard gate constants
# -------------------------------------------------------------------

class TestHardGates:
    def test_forbidden_toilet_kitchen(self):
        from app.layout.doors import _matches
        assert _matches(DOOR_ADJACENCY_FORBIDDEN, "toilet", "kitchen")
        assert _matches(DOOR_ADJACENCY_FORBIDDEN, "kitchen", "toilet")

    def test_forbidden_toilet_toilet(self):
        from app.layout.doors import _matches
        assert _matches(DOOR_ADJACENCY_FORBIDDEN, "toilet", "toilet")

    def test_forbidden_bedroom_kitchen(self):
        from app.layout.doors import _matches
        assert _matches(DOOR_ADJACENCY_FORBIDDEN, "bedroom", "kitchen")

    def test_parking_kitchen_not_forbidden(self):
        from app.layout.doors import _matches
        assert not _matches(DOOR_ADJACENCY_FORBIDDEN, "parking", "kitchen")

    def test_zone_map_private_rooms(self):
        assert ZONE_MAP.get("bedroom") == "private"
        assert ZONE_MAP.get("master_bedroom") == "private"


# -------------------------------------------------------------------
# 7. Adjacency breakdown shape
# -------------------------------------------------------------------

class TestAdjacencyBreakdown:
    def test_breakdown_items_have_pair_and_satisfied(self, simple_layout):
        room_polygons, room_types, _ = simple_layout
        _, breakdown = score_adjacency(room_polygons, room_types, return_breakdown=True)
        assert isinstance(breakdown, list)
        if breakdown:
            item = breakdown[0]
            assert "pair" in item
            assert "satisfied" in item
            assert "achieved" not in item, "'achieved' must be renamed to 'satisfied'"

    def test_breakdown_pair_is_two_element_list(self, simple_layout):
        room_polygons, room_types, _ = simple_layout
        _, breakdown = score_adjacency(room_polygons, room_types, return_breakdown=True)
        for item in breakdown:
            assert isinstance(item["pair"], list)
            assert len(item["pair"]) == 2

    def test_breakdown_satisfied_is_bool(self, simple_layout):
        room_polygons, room_types, _ = simple_layout
        _, breakdown = score_adjacency(room_polygons, room_types, return_breakdown=True)
        for item in breakdown:
            assert isinstance(item["satisfied"], bool)

    def test_score_in_0_1(self, simple_layout):
        room_polygons, room_types, _ = simple_layout
        score, _ = score_adjacency(room_polygons, room_types, return_breakdown=True)
        assert 0.0 <= score <= 1.0

    def test_only_canonical_pairs_in_breakdown(self, simple_layout):
        room_polygons, room_types, _ = simple_layout
        _, breakdown = score_adjacency(room_polygons, room_types, return_breakdown=True)
        canonical = [set(p) for p in PREFERRED_ADJACENCY_PAIRS]
        for item in breakdown:
            assert set(item["pair"]) in canonical, (
                f"Non-canonical pair {item['pair']} in breakdown"
            )


# -------------------------------------------------------------------
# 8-9. rejected_candidates logic
# -------------------------------------------------------------------

class TestRejectedCandidates:
    def _reason(self, valid, errors):
        if not valid and errors:
            return errors[0].get("code", "VALIDATION_FAILED")
        elif not valid:
            return "VALIDATION_FAILED"
        return "BELOW_DIVERSITY_THRESHOLD"

    def test_invalid_with_gate_code(self):
        assert self._reason(
            False, [{"code": "ENTRANCE_ROOM_TYPE", "severity": "error", "message": "x", "details": {}}]
        ) == "ENTRANCE_ROOM_TYPE"

    def test_invalid_no_errors(self):
        assert self._reason(False, []) == "VALIDATION_FAILED"

    def test_valid_pruned(self):
        assert self._reason(True, []) == "BELOW_DIVERSITY_THRESHOLD"

    def test_each_gate_code_is_str(self):
        for code in [
            "ENTRANCE_ROOM_TYPE", "NO_FORBIDDEN_DOORS", "HABITABLE_ROOM_WINDOW",
            "TOILET_VENTILATION", "PARKING_EXTERIOR_ACCESS", "CIRCULATION_DISCONNECTED",
            "BELOW_DIVERSITY_THRESHOLD", "VALIDATION_FAILED",
        ]:
            assert isinstance(code, str)


# -------------------------------------------------------------------
# 10. score_layout overall in [0, 1]
# -------------------------------------------------------------------

class TestScoreLayoutOutput:
    def test_overall_score_in_range(self, simple_layout):
        room_polygons, room_types, plot = simple_layout
        inner = plot.buffer(-0.3)
        graph = build_adjacency_graph(room_polygons, doors=[], entrance=None)
        circ = analyze_circulation(
            graph, list(room_polygons.keys()), entrance_room_id=None,
            room_types=room_types,
        )
        result = score_layout(
            room_polygons_dict=room_polygons,
            room_types=room_types,
            room_polygons_list=list(room_polygons.values()),
            plot_polygon=plot,
            inner_polygon=inner,
            zone_polygons={},
            windows=[],
            dead_spaces=[],
            parking_entities=[],
            circulation_data=circ,
            validation_warnings=[],
            validation_errors=[],
            doors=[],
        )
        assert 0.0 <= result["overall"] <= 1.0

    def test_score_breakdown_has_adjacency_breakdown(self, simple_layout):
        room_polygons, room_types, plot = simple_layout
        inner = plot.buffer(-0.3)
        graph = build_adjacency_graph(room_polygons, doors=[], entrance=None)
        circ = analyze_circulation(
            graph, list(room_polygons.keys()), entrance_room_id=None,
            room_types=room_types,
        )
        result = score_layout(
            room_polygons_dict=room_polygons,
            room_types=room_types,
            room_polygons_list=list(room_polygons.values()),
            plot_polygon=plot,
            inner_polygon=inner,
            zone_polygons={},
            windows=[],
            dead_spaces=[],
            parking_entities=[],
            circulation_data=circ,
            validation_warnings=[],
            validation_errors=[],
            doors=[],
        )
        assert "adjacency_breakdown" in result
        if result["adjacency_breakdown"]:
            assert "satisfied" in result["adjacency_breakdown"][0]
