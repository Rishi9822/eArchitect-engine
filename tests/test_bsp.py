"""
Tests for BSP layout generation.
"""
import pytest
from shapely.geometry import Polygon
from app.layout.bsp import (
    RoomSpec, generate_bsp_layout, build_room_specs,
    zone_partition, recursive_bsp, collect_leaves,
)
from app.config import SQ_FT_TO_SQ_M, FT_TO_M


def _make_specs(rooms):
    """Helper to build specs from simple list."""
    expanded = []
    for r in rooms:
        for i in range(r.get("count", 1)):
            expanded.append({
                "id": f"{r['type']}_{i}",
                "type": r["type"],
                "min_area_sqm": r["min_area"] * SQ_FT_TO_SQ_M,
                "priority": r.get("priority", 50),
            })
    return build_room_specs(expanded, {"parking": False})


class TestBSPGeneration:
    def test_rectangle_basic(self):
        poly = Polygon([(0, 0), (15, 0), (15, 12), (0, 12)])
        specs = _make_specs([
            {"type": "living", "count": 1, "min_area": 150},
            {"type": "bedroom", "count": 1, "min_area": 120},
            {"type": "kitchen", "count": 1, "min_area": 80},
        ])
        result = generate_bsp_layout(poly, specs, seed=42)
        assert len(result["room_leaves"]) >= 3
        for leaf in result["room_leaves"].values():
            assert leaf.polygon.is_valid

    def test_pentagon_layout(self):
        poly = Polygon([(0, 0), (18, 0), (20, 8), (10, 16), (0, 12)])
        inner = poly.buffer(-2.0, join_style=2)
        specs = _make_specs([
            {"type": "living", "count": 1, "min_area": 150},
            {"type": "dining", "count": 1, "min_area": 100},
            {"type": "bedroom", "count": 2, "min_area": 120},
            {"type": "kitchen", "count": 1, "min_area": 80},
        ])
        result = generate_bsp_layout(inner, specs, seed=42)
        assert len(result["room_leaves"]) >= 4

    def test_deterministic_with_seed(self):
        poly = Polygon([(0, 0), (15, 0), (15, 12), (0, 12)])
        specs = _make_specs([
            {"type": "living", "count": 1, "min_area": 150},
            {"type": "bedroom", "count": 2, "min_area": 120},
        ])
        r1 = generate_bsp_layout(poly, specs, seed=42)
        r2 = generate_bsp_layout(poly, specs, seed=42)

        # Same seed should produce same room IDs
        assert set(r1["room_leaves"].keys()) == set(r2["room_leaves"].keys())


class TestZonePartition:
    def test_zones_created(self):
        poly = Polygon([(0, 0), (20, 0), (20, 15), (0, 15)])
        specs = _make_specs([
            {"type": "living", "count": 1, "min_area": 150},
            {"type": "bedroom", "count": 1, "min_area": 120},
            {"type": "kitchen", "count": 1, "min_area": 80},
        ])
        from app.config import ZONE_MAP
        rooms_by_zone = {}
        for s in specs:
            rooms_by_zone.setdefault(s.zone, []).append(s)

        zones = zone_partition(poly, rooms_by_zone)
        assert len(zones) >= 2  # At least public and one other


class TestRecursiveBSP:
    def test_single_room(self):
        poly = Polygon([(0, 0), (10, 0), (10, 8), (0, 8)])
        spec = RoomSpec(id="living_0", type="living", zone="public",
                        min_area_sqm=10.0)
        node = recursive_bsp(poly, [spec])
        assert node.room is not None
        assert node.room.id == "living_0"

    def test_two_rooms(self):
        poly = Polygon([(0, 0), (20, 0), (20, 10), (0, 10)])
        specs = [
            RoomSpec(id="living_0", type="living", zone="public", min_area_sqm=30),
            RoomSpec(id="bedroom_0", type="bedroom", zone="private", min_area_sqm=20),
        ]
        node = recursive_bsp(poly, specs)
        leaves = collect_leaves(node)
        assigned = [l for l in leaves if l.room is not None]
        assert len(assigned) >= 2
