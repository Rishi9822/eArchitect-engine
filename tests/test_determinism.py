"""
Tests for determinism and seed repeatability.
"""
import pytest
from shapely.geometry import Polygon
from app.layout.bsp import build_room_specs, generate_bsp_layout
from app.config import SQ_FT_TO_SQ_M


class TestDeterminism:
    def test_exact_determinism_with_same_seed(self):
        poly = Polygon([(0, 0), (18, 0), (20, 8), (10, 16), (0, 12)])
        inner = poly.buffer(-2.0, join_style=2)
        specs = build_room_specs([
            {"id": "living_0", "type": "living", "min_area_sqm": 150 * SQ_FT_TO_SQ_M, "priority": 10},
            {"id": "dining_0", "type": "dining", "min_area_sqm": 100 * SQ_FT_TO_SQ_M, "priority": 15},
            {"id": "bedroom_0", "type": "bedroom", "min_area_sqm": 120 * SQ_FT_TO_SQ_M, "priority": 20},
            {"id": "kitchen_0", "type": "kitchen", "min_area_sqm": 80 * SQ_FT_TO_SQ_M, "priority": 25},
        ], {"parking": True})

        run1 = generate_bsp_layout(inner, specs, seed=12345)
        run2 = generate_bsp_layout(inner, specs, seed=12345)

        assert set(run1["room_leaves"].keys()) == set(run2["room_leaves"].keys())
        for rid in run1["room_leaves"]:
            p1 = run1["room_leaves"][rid].polygon
            p2 = run2["room_leaves"][rid].polygon
            assert abs(p1.area - p2.area) < 1e-5
            assert abs(p1.centroid.x - p2.centroid.x) < 1e-5
            assert abs(p1.centroid.y - p2.centroid.y) < 1e-5
