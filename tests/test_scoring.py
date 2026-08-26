"""
Tests for scoring system.
"""
import pytest
from shapely.geometry import Polygon
from app.scoring.scorer import score_layout, _score_buildable_utilization, _score_building_coverage
from app.scoring.adjacency import score_adjacency
from app.scoring.metrics import score_natural_light, score_ventilation, score_dead_space


class TestUtilizationScoring:
    def test_full_utilization(self):
        inner = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        rooms = [inner]  # Room fills entire area
        score = _score_buildable_utilization(rooms, inner)
        assert abs(score - 1.0) < 0.01

    def test_half_utilization(self):
        inner = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        room = Polygon([(0, 0), (5, 0), (5, 10), (0, 10)])  # Half
        score = _score_buildable_utilization([room], inner)
        assert abs(score - 0.5) < 0.05


class TestBuildingCoverage:
    def test_moderate_coverage(self):
        """50% coverage should score well."""
        plot = Polygon([(0, 0), (20, 0), (20, 20), (0, 20)])  # 400 sqm
        rooms = [Polygon([(0, 0), (10, 0), (10, 20), (0, 20)])]  # 200 sqm = 50%
        score = _score_building_coverage(rooms, plot)
        assert score >= 0.8

    def test_very_low_coverage(self):
        """10% coverage should penalise."""
        plot = Polygon([(0, 0), (20, 0), (20, 20), (0, 20)])
        rooms = [Polygon([(0, 0), (2, 0), (2, 20), (0, 20)])]  # 40 = 10%
        score = _score_building_coverage(rooms, plot)
        assert score < 0.8


class TestAdjacencyScoring:
    def test_adjacent_living_kitchen(self):
        room_a = Polygon([(0, 0), (5, 0), (5, 5), (0, 5)])
        room_b = Polygon([(5, 0), (10, 0), (10, 5), (5, 5)])
        polys = {"living_0": room_a, "kitchen_0": room_b}
        types = {"living_0": "living", "kitchen_0": "kitchen"}
        score = score_adjacency(polys, types, {})
        assert score > 0  # Should get some credit


class TestNaturalLightScoring:
    def test_room_with_exterior_and_window(self):
        room = Polygon([(0, 0), (5, 0), (5, 5), (0, 5)])
        boundary = Polygon([(0, 0), (10, 0), (10, 5), (0, 5)])
        polys = {"bedroom_0": room}
        types = {"bedroom_0": "bedroom"}
        windows = [{"room_id": "bedroom_0"}]
        score = score_natural_light(polys, types, boundary, windows)
        assert score >= 0.8


class TestDeadSpaceScoring:
    def test_no_dead_space(self):
        inner = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        score = score_dead_space([], inner)
        assert score == 1.0

    def test_unusable_dead_space(self):
        inner = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        dead = [{"area_sqm": 20, "classification": "unusable"}]
        score = score_dead_space(dead, inner)
        assert score < 1.0


class TestFullScoring:
    def test_score_returns_all_metrics(self):
        inner = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        plot = Polygon([(0, 0), (12, 0), (12, 12), (0, 12)])
        room = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        room_dict = {"living_0": room}
        types = {"living_0": "living"}

        result = score_layout(
            room_polygons_dict=room_dict,
            room_types=types,
            room_polygons_list=[room],
            plot_polygon=plot,
            inner_polygon=inner,
            zone_polygons={"public": room},
            windows=[],
            dead_spaces=[],
            parking_entities=[],
            circulation_data={"score": 0.8},
            validation_warnings=[],
            validation_errors=[],
        )

        assert "overall" in result
        assert 0 <= result["overall"] <= 1
        assert "buildable_utilization" in result
        assert "building_coverage" in result
        assert "adjacency" in result
        assert "natural_light" in result
