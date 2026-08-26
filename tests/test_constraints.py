"""
Tests for room constraints and feasibility.
"""
import pytest
from shapely.geometry import Polygon
from app.layout.constraints import check_feasibility
from app.layout.bsp import RoomSpec


class TestFeasibility:
    def test_feasible_layout(self):
        poly = Polygon([(0, 0), (20, 0), (20, 15), (0, 15)])  # 300 sqm
        specs = [
            RoomSpec(id="living_0", type="living", zone="public", min_area_sqm=15),
            RoomSpec(id="bedroom_0", type="bedroom", zone="private", min_area_sqm=12),
        ]
        result = check_feasibility(specs, poly)
        assert result.feasible is True

    def test_infeasible_total_area(self):
        poly = Polygon([(0, 0), (5, 0), (5, 5), (0, 5)])  # 25 sqm
        specs = [
            RoomSpec(id="living_0", type="living", zone="public", min_area_sqm=15),
            RoomSpec(id="bedroom_0", type="bedroom", zone="private", min_area_sqm=12),
            RoomSpec(id="kitchen_0", type="kitchen", zone="service", min_area_sqm=8),
        ]
        # 35 sqm required > 22.5 sqm usable (25 * 0.9)
        result = check_feasibility(specs, poly)
        assert result.feasible is False
        assert len(result.messages) > 0

    def test_single_room_too_large(self):
        poly = Polygon([(0, 0), (5, 0), (5, 5), (0, 5)])  # 25 sqm
        specs = [
            RoomSpec(id="living_0", type="living", zone="public", min_area_sqm=30),
        ]
        result = check_feasibility(specs, poly)
        assert result.feasible is False
