"""
Tests for estimator geometric measurements.
"""
import pytest
from shapely.geometry import Polygon
from app.geometry.measurements import compute_measurements


class TestMeasurements:
    def test_measurements_calculation(self):
        plot = Polygon([(0, 0), (20, 0), (20, 15), (0, 15)])  # 300 sqm
        inner = Polygon([(2, 2), (18, 2), (18, 13), (2, 13)]) # 176 sqm
        room_a = Polygon([(2, 2), (10, 2), (10, 13), (2, 13)])
        room_b = Polygon([(10, 2), (18, 2), (18, 13), (10, 13)])
        walls = [
            {"type": "exterior", "length": 54.0},
            {"type": "interior", "length": 11.0},
        ]
        doors = [{"id": "D001"}]
        windows = [{"id": "WIN001"}, {"id": "WIN002"}]

        m = compute_measurements(
            plot_polygon=plot,
            inner_polygon=inner,
            room_polygons=[room_a, room_b],
            walls=walls,
            doors=doors,
            windows=windows,
            floor_height_m=3.0,
        )

        assert m["plot_area_sqm"] == 300.0
        assert m["plot_area_sqft"] > 3000.0
        assert m["buildable_area_sqm"] == 176.0
        assert m["room_area_sqm"] == 176.0
        assert m["exterior_wall_length_m"] == 54.0
        assert m["interior_wall_length_m"] == 11.0
        assert m["total_wall_length_m"] == 65.0
        assert m["exterior_wall_area_sqm"] == 162.0  # 54 * 3
        assert m["interior_wall_area_sqm"] == 33.0   # 11 * 3
        assert m["total_door_count"] == 1
        assert m["total_window_count"] == 2
