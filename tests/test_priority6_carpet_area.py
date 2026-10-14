"""
Priority 6 – Wall Thickness & Carpet Area Accounting

Tests for:
1. Insetting room polygons by half wall thickness to produce true carpet polygons.
2. Carpet area, built-up area, and super built-up area calculations.
3. Geometric conservation assertion:
   sum(carpet_area) + sum(corridor_area) + total_wall_footprint_area == buildable_area (within 0.01 sqm).
4. Masonry wall volume (length * thickness * height) in m³ and cu ft.
5. Model fields and API response integration.
"""
import pytest
from shapely.geometry import Polygon, LineString, box
from fastapi.testclient import TestClient

from app.main import app
from app.config import (
    EXTERIOR_WALL_THICKNESS,
    INTERIOR_WALL_THICKNESS,
    SQ_M_TO_SQ_FT,
    M3_TO_CU_FT,
)
from app.geometry.carpet_area import (
    compute_room_carpet_polygon,
    compute_layout_carpet_accounting,
)
from app.geometry.measurements import compute_measurements
from app.models.output_models import RoomOutput, MeasurementsOutput, Coordinate


# ═══════════════════════════════════════════════════
# 1. CARPET POLYGON INSET UNIT TESTS
# ═══════════════════════════════════════════════════

class TestCarpetPolygonInset:
    """Verify edge-by-edge insetting by half wall thickness."""

    def test_rectangular_room_inset(self):
        # 5m x 4m room (20 sqm)
        room_poly = box(0, 0, 5, 4)
        # 4 bounding walls: left & bottom interior, right & top exterior
        walls = [
            {"start": {"x": 0, "y": 0}, "end": {"x": 5, "y": 0}, "thickness": INTERIOR_WALL_THICKNESS, "type": "interior"},
            {"start": {"x": 5, "y": 0}, "end": {"x": 5, "y": 4}, "thickness": EXTERIOR_WALL_THICKNESS, "type": "exterior"},
            {"start": {"x": 5, "y": 4}, "end": {"x": 0, "y": 4}, "thickness": EXTERIOR_WALL_THICKNESS, "type": "exterior"},
            {"start": {"x": 0, "y": 4}, "end": {"x": 0, "y": 0}, "thickness": INTERIOR_WALL_THICKNESS, "type": "interior"},
        ]
        carpet_poly, wall_fp = compute_room_carpet_polygon(room_poly, walls)

        assert carpet_poly.is_valid
        assert not carpet_poly.is_empty
        assert carpet_poly.geom_type == "Polygon"
        assert carpet_poly.area < room_poly.area
        assert abs(carpet_poly.area + wall_fp - room_poly.area) < 1e-6

        # Inward bounds check:
        # xmin should be approx 0 + INTERIOR_WALL_THICKNESS/2
        # xmax should be approx 5 - EXTERIOR_WALL_THICKNESS/2
        # ymin should be approx 0 + INTERIOR_WALL_THICKNESS/2
        # ymax should be approx 4 - EXTERIOR_WALL_THICKNESS/2
        minx, miny, maxx, maxy = carpet_poly.bounds
        assert minx > 0.0
        assert miny > 0.0
        assert maxx < 5.0
        assert maxy < 4.0
        assert abs(minx - INTERIOR_WALL_THICKNESS / 2.0) < 1e-3
        assert abs(maxx - (5.0 - EXTERIOR_WALL_THICKNESS / 2.0)) < 1e-3

    def test_l_shaped_room_inset(self):
        # L-shaped room
        room_poly = Polygon([(0, 0), (6, 0), (6, 3), (3, 3), (3, 6), (0, 6)])
        carpet_poly, wall_fp = compute_room_carpet_polygon(room_poly, walls=None)

        assert carpet_poly.is_valid
        assert not carpet_poly.is_empty
        assert carpet_poly.area < room_poly.area
        assert abs(carpet_poly.area + wall_fp - room_poly.area) < 1e-6

    def test_tiny_room_fallback(self):
        # Extremely small room that would collapse under normal offset
        tiny_poly = box(0, 0, 0.1, 0.1)
        carpet_poly, wall_fp = compute_room_carpet_polygon(tiny_poly, walls=None)

        assert carpet_poly.is_valid
        assert not carpet_poly.is_empty
        assert carpet_poly.area <= tiny_poly.area


# ═══════════════════════════════════════════════════
# 2. CONSERVATION ASSERTION TESTS
# ═══════════════════════════════════════════════════

class TestAreaConservation:
    """Verify sum(carpet) + sum(corridor) + total_wall_footprint == buildable_area."""

    def test_two_room_conservation(self):
        inner = box(0, 0, 10, 6)  # 60 sqm
        r1 = box(0, 0, 5, 6)      # 30 sqm
        r2 = box(5, 0, 10, 6)     # 30 sqm
        room_polys = {"r1": r1, "r2": r2}

        walls = [
            {"start": {"x": 0, "y": 0}, "end": {"x": 10, "y": 0}, "thickness": EXTERIOR_WALL_THICKNESS, "length": 10.0, "type": "exterior"},
            {"start": {"x": 10, "y": 0}, "end": {"x": 10, "y": 6}, "thickness": EXTERIOR_WALL_THICKNESS, "length": 6.0, "type": "exterior"},
            {"start": {"x": 10, "y": 6}, "end": {"x": 0, "y": 6}, "thickness": EXTERIOR_WALL_THICKNESS, "length": 10.0, "type": "exterior"},
            {"start": {"x": 0, "y": 6}, "end": {"x": 0, "y": 0}, "thickness": EXTERIOR_WALL_THICKNESS, "length": 6.0, "type": "exterior"},
            {"start": {"x": 5, "y": 0}, "end": {"x": 5, "y": 6}, "thickness": INTERIOR_WALL_THICKNESS, "length": 6.0, "type": "interior"},
        ]

        acct = compute_layout_carpet_accounting(
            room_polygons=room_polys,
            walls=walls,
            inner_polygon=inner,
        )

        assert acct["conservation_valid"] is True
        assert acct["conservation_error_sqm"] <= 0.01
        assert abs(acct["conservation_sum_sqm"] - inner.area) <= 0.01

    def test_corridor_and_dead_space_conservation(self):
        inner = box(0, 0, 10, 10)  # 100 sqm
        r1 = box(0, 0, 5, 8)       # 40 sqm
        r2 = box(5, 0, 10, 8)      # 40 sqm
        corr = box(0, 8, 8, 10)    # 16 sqm
        dead = box(8, 8, 10, 10)   # 4 sqm
        # 40 + 40 + 16 + 4 = 100 sqm

        room_polys = {"r1": r1, "r2": r2}
        corridors = [{"id": "c1", "area_sqm": 16.0}]
        dead_spaces = [{"id": "d1", "area_sqm": 4.0}]

        acct = compute_layout_carpet_accounting(
            room_polygons=room_polys,
            walls=[],
            corridors=corridors,
            corridor_polygons=[corr],
            dead_spaces=dead_spaces,
            inner_polygon=inner,
        )

        assert acct["conservation_valid"] is True
        assert acct["total_corridor_area_sqm"] == 16.0
        assert acct["total_dead_space_area_sqm"] == 4.0
        assert abs(acct["conservation_sum_sqm"] - 100.0) <= 0.01


# ═══════════════════════════════════════════════════
# 3. SUPER BUILT-UP & LOADING FACTOR TESTS
# ═══════════════════════════════════════════════════

class TestSuperBuiltUpAccounting:
    """Verify super built-up area distribution with common loading."""

    def test_super_built_up_without_corridor(self):
        r1 = box(0, 0, 4, 5)  # 20 sqm
        r2 = box(4, 0, 8, 5)  # 20 sqm
        acct = compute_layout_carpet_accounting(
            room_polygons={"r1": r1, "r2": r2},
            walls=[],
            corridors=None,
        )
        # Without corridors, super built-up == built-up
        assert acct["per_room"]["r1"]["super_built_up_area_sqm"] == 20.0
        assert acct["per_room"]["r2"]["super_built_up_area_sqm"] == 20.0
        assert acct["total_super_built_up_area_sqm"] == 40.0

    def test_super_built_up_with_corridor_loading(self):
        r1 = box(0, 0, 5, 4)  # 20 sqm
        r2 = box(0, 4, 5, 8)  # 20 sqm
        # Corridor: 10 sqm
        # Total built-up = 50 sqm. Rooms gross = 40 sqm. Loading factor = 50/40 = 1.25
        corridors = [{"id": "c1", "area_sqm": 10.0}]
        acct = compute_layout_carpet_accounting(
            room_polygons={"r1": r1, "r2": r2},
            walls=[],
            corridors=corridors,
            corridor_polygons=[box(5, 0, 6, 10)],
        )
        # Each 20 sqm room should get 20 * 1.25 = 25 sqm super built-up
        assert abs(acct["per_room"]["r1"]["super_built_up_area_sqm"] - 25.0) < 1e-4
        assert abs(acct["per_room"]["r2"]["super_built_up_area_sqm"] - 25.0) < 1e-4
        # Sum of rooms super built-up equals total built-up
        sum_sb = sum(r["super_built_up_area_sqm"] for r in acct["per_room"].values())
        assert abs(sum_sb - acct["total_super_built_up_area_sqm"]) < 1e-4


# ═══════════════════════════════════════════════════
# 4. MASONRY WALL VOLUME TESTS
# ═══════════════════════════════════════════════════

class TestMasonryWallVolume:
    """Verify wall volume calculation: length * thickness * height."""

    def test_volume_calculation(self):
        walls = [
            {"type": "exterior", "length": 20.0, "thickness": 0.2286},
            {"type": "interior", "length": 10.0, "thickness": 0.1143},
        ]
        # Exterior: 20 * 0.2286 * 3.0 = 13.716 m³
        # Interior: 10 * 0.1143 * 3.0 = 3.429 m³
        # Total = 17.145 m³
        meas = compute_measurements(
            plot_polygon=box(0, 0, 15, 10),
            inner_polygon=box(1, 1, 14, 9),
            room_polygons=[box(1, 1, 14, 9)],
            walls=walls,
            doors=[],
            windows=[],
            floor_height_m=3.0,
        )

        assert abs(meas["masonry_wall_volume_m3"] - 17.145) < 1e-3
        expected_cuft = 17.145 * M3_TO_CU_FT
        assert abs(meas["masonry_wall_volume_cuft"] - expected_cuft) < 0.1


# ═══════════════════════════════════════════════════
# 5. OUTPUT MODELS & API RESPONSE INTEGRATION
# ═══════════════════════════════════════════════════

class TestPriority6APIIntegration:
    """Verify carpet area and wall accounting fields in live API response."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    @pytest.fixture
    def basic_payload(self):
        return {
            "plot": {
                "points": [
                    {"x": 0, "y": 0}, {"x": 15, "y": 0},
                    {"x": 15, "y": 12}, {"x": 0, "y": 12},
                ],
                "facing": "north",
                "road_side": "front",
                "setback": 1.5,
            },
            "rooms": [
                {"type": "living", "count": 1, "min_area": 150},
                {"type": "bedroom", "count": 1, "min_area": 120},
                {"type": "kitchen", "count": 1, "min_area": 80},
                {"type": "toilet", "count": 1, "min_area": 40},
            ],
            "entrance": {"side": "front", "width": 1.2},
            "preferences": {},
            "seed": 42,
        }

    def test_room_output_contains_carpet_fields(self, client, basic_payload):
        resp = client.post("/api/v1/layouts/generate", json=basic_payload)
        assert resp.status_code == 200
        data = resp.json()
        cand = data["candidates"][0]

        for r in cand["rooms"]:
            assert "carpet_area_sqm" in r
            assert "carpet_area_sqft" in r
            assert "carpet_polygon" in r
            assert "built_up_area_sqm" in r
            assert "super_built_up_area_sqm" in r
            assert "wall_footprint_area_sqm" in r
            assert r["carpet_area_sqm"] > 0
            assert r["carpet_area_sqm"] <= r["built_up_area_sqm"]
            assert len(r["carpet_polygon"]) >= 3

    def test_measurements_contain_priority6_fields(self, client, basic_payload):
        resp = client.post("/api/v1/layouts/generate", json=basic_payload)
        assert resp.status_code == 200
        data = resp.json()
        cand = data["candidates"][0]
        m = cand["measurements"]

        assert "carpet_area_sqm" in m
        assert "carpet_area_sqft" in m
        assert "super_built_up_area_sqm" in m
        assert "total_wall_footprint_area_sqm" in m
        assert "masonry_wall_volume_m3" in m
        assert "masonry_wall_volume_cuft" in m

        assert m["carpet_area_sqm"] > 0
        assert m["masonry_wall_volume_m3"] > 0
        assert m["masonry_wall_volume_cuft"] > 0

    def test_live_api_area_conservation(self, client, basic_payload):
        resp = client.post("/api/v1/layouts/generate", json=basic_payload)
        assert resp.status_code == 200
        data = resp.json()
        cand = data["candidates"][0]
        m = cand["measurements"]
        buildable = data["buildable_area"]["area_sqm"]

        carpet = m["carpet_area_sqm"]
        corridor = m.get("corridor_area_sqm", 0.0)
        wall_fp = m["total_wall_footprint_area_sqm"]

        conservation_sum = carpet + corridor + wall_fp
        diff = abs(conservation_sum - buildable)
        assert diff <= 0.01, f"Conservation error {diff:.6f} exceeds 0.01 sqm threshold"
