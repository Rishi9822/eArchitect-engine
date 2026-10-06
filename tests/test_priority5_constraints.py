"""
Priority 5 – Ventilation / Natural Light Validation & Constraints Audit

Tests for the individual auditable constraint functions in app.layout.constraints,
plus the integrated ventilation fields and NATURAL_LIGHT_HABITABLE / TOILET_NO_VENTILATION
gates wired into layout_service._process_single_candidate.
"""
import pytest
from shapely.geometry import Polygon

from app.layout.constraints import (
    HARD_CONSTRAINTS,
    HABITABLE_ROOM_TYPES,
    ENTRANCE_FORBIDDEN_TYPES,
    check_room_completeness,
    check_room_area_minimum,
    check_room_no_overlap,
    check_room_valid_geometry,
    check_room_inside_boundary,
    check_room_dimension_minimum,
    check_room_aspect_ratio,
    check_circulation_connected,
    check_entrance_room_type,
    check_no_forbidden_doors,
    check_habitable_room_window,
    check_natural_light_habitable,
    check_toilet_ventilation,
    check_parking_exterior_access,
    check_parking_dimensions,
)
from app.layout.bsp import RoomSpec


# ═══════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════

def _box(x0, y0, x1, y1):
    """Create an axis-aligned rectangular polygon."""
    return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def _make_spec(room_id, room_type="bedroom", min_area=10.0, min_width=2.5, max_ar=3.0, zone="private"):
    """Helper to create a RoomSpec."""
    return RoomSpec(
        id=room_id,
        type=room_type,
        zone=zone,
        min_area_sqm=min_area,
        min_width_m=min_width,
        min_length_m=min_width,
        max_aspect_ratio=max_ar,
        priority=50,
        requires_exterior_wall=True,
    )


# ═══════════════════════════════════════════════════
# 1. HARD_CONSTRAINTS LIST
# ═══════════════════════════════════════════════════

class TestHardConstraintsList:
    """Verify the HARD_CONSTRAINTS list contains all audited codes."""

    def test_contains_all_expected_codes(self):
        expected = {
            "ROOM_COMPLETENESS", "ROOM_AREA_MINIMUM", "ROOM_NO_OVERLAP",
            "ROOM_VALID_GEOMETRY", "ROOM_INSIDE_BOUNDARY",
            "CIRCULATION_CONNECTED", "ENTRANCE_ROOM_TYPE",
            "NO_FORBIDDEN_DOORS", "HABITABLE_ROOM_WINDOW",
            "NATURAL_LIGHT_HABITABLE", "TOILET_NO_VENTILATION",
            "PARKING_EXTERIOR_ACCESS",
        }
        for code in expected:
            assert code in HARD_CONSTRAINTS, f"{code} missing from HARD_CONSTRAINTS"

    def test_no_duplicates(self):
        assert len(HARD_CONSTRAINTS) == len(set(HARD_CONSTRAINTS))


# ═══════════════════════════════════════════════════
# 2. ROOM_COMPLETENESS
# ═══════════════════════════════════════════════════

class TestRoomCompleteness:
    def test_all_placed(self):
        specs = [_make_spec("r1"), _make_spec("r2")]
        errs = check_room_completeness(specs, {"r1", "r2"})
        assert errs == []

    def test_missing_room(self):
        specs = [_make_spec("r1"), _make_spec("r2")]
        errs = check_room_completeness(specs, {"r1"})
        assert len(errs) == 1
        assert errs[0]["code"] == "ROOM_COMPLETENESS"
        assert "r2" in errs[0]["message"]


# ═══════════════════════════════════════════════════
# 3. ROOM_AREA_MINIMUM
# ═══════════════════════════════════════════════════

class TestRoomAreaMinimum:
    def test_area_ok(self):
        polys = {"r1": _box(0, 0, 5, 5)}  # 25 sqm
        specs = {"r1": _make_spec("r1", min_area=20.0)}
        errs = check_room_area_minimum(polys, specs)
        assert errs == []

    def test_area_below_min(self):
        polys = {"r1": _box(0, 0, 2, 2)}  # 4 sqm
        specs = {"r1": _make_spec("r1", min_area=20.0)}
        errs = check_room_area_minimum(polys, specs, strict=True)
        assert len(errs) == 1
        assert errs[0]["code"] == "ROOM_AREA_MINIMUM"


# ═══════════════════════════════════════════════════
# 4. ROOM_NO_OVERLAP
# ═══════════════════════════════════════════════════

class TestRoomNoOverlap:
    def test_no_overlap(self):
        polys = {"r1": _box(0, 0, 5, 5), "r2": _box(5, 0, 10, 5)}
        errs = check_room_no_overlap(polys)
        assert errs == []

    def test_overlap_detected(self):
        polys = {"r1": _box(0, 0, 5, 5), "r2": _box(3, 0, 8, 5)}
        errs = check_room_no_overlap(polys)
        assert len(errs) == 1
        assert errs[0]["code"] == "ROOM_NO_OVERLAP"


# ═══════════════════════════════════════════════════
# 5. ROOM_VALID_GEOMETRY
# ═══════════════════════════════════════════════════

class TestRoomValidGeometry:
    def test_valid_polygon(self):
        polys = {"r1": _box(0, 0, 5, 5)}
        errs = check_room_valid_geometry(polys)
        assert errs == []

    def test_empty_polygon(self):
        polys = {"r1": Polygon()}
        errs = check_room_valid_geometry(polys)
        assert len(errs) == 1
        assert errs[0]["code"] == "ROOM_VALID_GEOMETRY"


# ═══════════════════════════════════════════════════
# 6. ROOM_INSIDE_BOUNDARY
# ═══════════════════════════════════════════════════

class TestRoomInsideBoundary:
    def test_room_inside(self):
        boundary = _box(0, 0, 20, 20)
        polys = {"r1": _box(1, 1, 5, 5)}
        errs = check_room_inside_boundary(polys, boundary)
        assert errs == []

    def test_room_outside(self):
        boundary = _box(0, 0, 10, 10)
        polys = {"r1": _box(8, 8, 15, 15)}
        errs = check_room_inside_boundary(polys, boundary, max_outside_pct=1.0)
        assert len(errs) == 1
        assert errs[0]["code"] == "ROOM_INSIDE_BOUNDARY"


# ═══════════════════════════════════════════════════
# 7. CIRCULATION_CONNECTED
# ═══════════════════════════════════════════════════

class TestCirculationConnected:
    def test_connected(self):
        errs = check_circulation_connected({"connected": True})
        assert errs == []

    def test_disconnected(self):
        errs = check_circulation_connected({"connected": False, "reachable_rooms": 3, "total_rooms": 5})
        assert len(errs) == 1
        assert errs[0]["code"] == "CIRCULATION_CONNECTED"


# ═══════════════════════════════════════════════════
# 8. ENTRANCE_ROOM_TYPE
# ═══════════════════════════════════════════════════

class TestEntranceRoomType:
    def test_valid_entrance(self):
        errs = check_entrance_room_type("living", room_id="r1")
        assert errs == []

    def test_forbidden_entrance_types(self):
        for rtype in ENTRANCE_FORBIDDEN_TYPES:
            errs = check_entrance_room_type(rtype, room_id="r1")
            assert len(errs) == 1, f"Expected ENTRANCE_ROOM_TYPE error for type '{rtype}'"
            assert errs[0]["code"] == "ENTRANCE_ROOM_TYPE"


# ═══════════════════════════════════════════════════
# 9. HABITABLE_ROOM_WINDOW
# ═══════════════════════════════════════════════════

class TestHabitableRoomWindow:
    def test_habitable_with_window(self):
        room_types = {"r1": "living"}
        errs = check_habitable_room_window(room_types, rooms_with_windows={"r1"})
        assert errs == []

    def test_habitable_without_window(self):
        room_types = {"r1": "bedroom"}
        errs = check_habitable_room_window(room_types, rooms_with_windows=set())
        assert len(errs) == 1
        assert errs[0]["code"] == "HABITABLE_ROOM_WINDOW"

    def test_non_habitable_no_window_ok(self):
        room_types = {"r1": "kitchen"}
        errs = check_habitable_room_window(room_types, rooms_with_windows=set())
        assert errs == []


# ═══════════════════════════════════════════════════
# 10. NATURAL_LIGHT_HABITABLE
# ═══════════════════════════════════════════════════

class TestNaturalLightHabitable:
    def test_sufficient_window_area(self):
        """A 20sqm room with a 1.8m x 1.2m window (2.16sqm >= 2.0sqm needed) passes."""
        room_polygons = {"r1": _box(0, 0, 5, 4)}  # 20 sqm
        room_types = {"r1": "living"}
        windows = [{"room_id": "r1", "width": 1.8, "height_m": 1.2, "type": "standard"}]
        errs = check_natural_light_habitable(room_polygons, room_types, windows)
        assert errs == [], f"Expected no errors but got: {errs}"

    def test_insufficient_window_area(self):
        """A 30sqm room needs >=3.0sqm window. 0.6m x 1.2m = 0.72 sqm fails."""
        room_polygons = {"r1": _box(0, 0, 6, 5)}  # 30 sqm
        room_types = {"r1": "bedroom"}
        windows = [{"room_id": "r1", "width": 0.6, "height_m": 1.2, "type": "standard"}]
        errs = check_natural_light_habitable(room_polygons, room_types, windows)
        assert len(errs) == 1
        assert errs[0]["code"] == "NATURAL_LIGHT_HABITABLE"
        assert errs[0]["details"]["ratio"] < 0.10

    def test_multiple_windows_sum(self):
        """Two windows whose combined area meets 10% should pass."""
        room_polygons = {"r1": _box(0, 0, 5, 4)}  # 20 sqm, needs >= 2.0 sqm
        room_types = {"r1": "dining"}
        windows = [
            {"room_id": "r1", "width": 1.0, "height_m": 1.2, "type": "standard"},  # 1.2
            {"room_id": "r1", "width": 0.8, "height_m": 1.2, "type": "standard"},  # 0.96
        ]
        # Total = 2.16 >= 2.0
        errs = check_natural_light_habitable(room_polygons, room_types, windows)
        assert errs == []

    def test_non_habitable_room_ignored(self):
        """Kitchen (non-habitable) should not be checked."""
        room_polygons = {"r1": _box(0, 0, 5, 4)}
        room_types = {"r1": "kitchen"}
        windows = []
        errs = check_natural_light_habitable(room_polygons, room_types, windows)
        assert errs == []

    def test_zero_windows_fails(self):
        """Habitable room with no windows at all fails."""
        room_polygons = {"r1": _box(0, 0, 4, 4)}  # 16 sqm
        room_types = {"r1": "study"}
        errs = check_natural_light_habitable(room_polygons, room_types, [])
        assert len(errs) == 1
        assert errs[0]["code"] == "NATURAL_LIGHT_HABITABLE"


# ═══════════════════════════════════════════════════
# 11. TOILET_NO_VENTILATION / TOILET_VENTILATION
# ═══════════════════════════════════════════════════

class TestToiletVentilation:
    def test_toilet_with_window(self):
        room_polygons = {"t1": _box(0, 0, 2, 2)}
        room_types = {"t1": "toilet"}
        errs = check_toilet_ventilation(room_polygons, room_types, rooms_with_windows={"t1"})
        assert errs == []

    def test_toilet_adjacent_to_corridor(self):
        toilet_poly = _box(0, 0, 2, 2)
        corridor_poly = _box(2, 0, 4, 2)
        room_polygons = {"t1": toilet_poly}
        room_types = {"t1": "toilet"}
        errs = check_toilet_ventilation(
            room_polygons, room_types,
            rooms_with_windows=set(),
            corridor_polys=[corridor_poly],
        )
        assert errs == []

    def test_toilet_adjacent_to_utility(self):
        toilet_poly = _box(0, 0, 2, 2)
        utility_poly = _box(2, 0, 4, 2)
        room_polygons = {"t1": toilet_poly, "util_0": utility_poly}
        room_types = {"t1": "toilet", "util_0": "utility"}
        errs = check_toilet_ventilation(
            room_polygons, room_types,
            rooms_with_windows=set(),
            corridor_polys=None,
            other_polygons=room_polygons,
        )
        assert errs == []

    def test_toilet_no_ventilation(self):
        room_polygons = {"t1": _box(5, 5, 7, 7)}
        room_types = {"t1": "toilet"}
        errs = check_toilet_ventilation(
            room_polygons, room_types,
            rooms_with_windows=set(),
            corridor_polys=None,
            other_polygons=None,
        )
        assert len(errs) == 1
        assert errs[0]["code"] == "TOILET_NO_VENTILATION"


# ═══════════════════════════════════════════════════
# 12. PARKING_EXTERIOR_ACCESS
# ═══════════════════════════════════════════════════

class TestParkingExteriorAccess:
    def test_parking_with_access(self):
        entities = [{"id": "p1", "road_access": True}]
        errs = check_parking_exterior_access(entities)
        assert errs == []

    def test_parking_without_access(self):
        entities = [{"id": "p1", "road_access": False}]
        errs = check_parking_exterior_access(entities)
        assert len(errs) == 1
        assert errs[0]["code"] == "PARKING_EXTERIOR_ACCESS"


# ═══════════════════════════════════════════════════
# 13. PARKING_DIMENSIONS
# ═══════════════════════════════════════════════════

class TestParkingDimensions:
    def test_parking_meets_minimum(self):
        entities = [{"id": "p1", "meets_minimum": True}]
        errs = check_parking_dimensions(entities)
        assert errs == []

    def test_parking_too_small(self):
        entities = [{"id": "p1", "meets_minimum": False}]
        errs = check_parking_dimensions(entities, strict=True)
        assert len(errs) == 1
        assert errs[0]["code"] == "PARKING_DIMENSIONS"


# ═══════════════════════════════════════════════════
# 14. INTEGRATION: RoomOutput ventilation fields
# ═══════════════════════════════════════════════════

class TestRoomOutputVentilationFields:
    """Verify the output model accepts the new ventilation fields."""

    def test_room_output_has_ventilation_fields(self):
        from app.models.output_models import RoomOutput
        room = RoomOutput(
            id="r1", type="toilet",
            area_sqft=40.0, area_sqm=3.72,
            polygon=[{"x": 0, "y": 0}, {"x": 2, "y": 0}, {"x": 2, "y": 2}, {"x": 0, "y": 2}],
            centroid={"x": 1.0, "y": 1.0},
            aspect_ratio=1.0,
            zone="service",
            has_ventilation=True,
            mechanical_ventilation=True,
            ventilation_shaft=False,
        )
        assert room.has_ventilation is True
        assert room.mechanical_ventilation is True
        assert room.ventilation_shaft is False

    def test_window_output_has_area_and_height(self):
        from app.models.output_models import WindowOutput
        from app.models.common import Coordinate
        win = WindowOutput(
            id="w1",
            room_id="r1",
            position=Coordinate(x=0.0, y=0.0),
            width=1.2,
            height_m=1.2,
            area_sqm=1.44,
            type="standard",
            sill_height_m=0.9,
        )
        assert win.height_m == 1.2
        assert win.area_sqm == 1.44


# ═══════════════════════════════════════════════════
# 15. END-TO-END: constraints_checked in API response
# ═══════════════════════════════════════════════════

class TestConstraintsCheckedInResponse:
    """Verify the API response includes all audited constraint codes."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from app.main import app
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

    def test_constraints_checked_includes_natural_light(self, client, basic_payload):
        resp = client.post("/api/v1/layouts/generate", json=basic_payload)
        assert resp.status_code == 200
        data = resp.json()
        cand = data["candidates"][0]
        checked = cand["validation"]["constraints_checked"]
        assert "NATURAL_LIGHT_HABITABLE" in checked
        assert "TOILET_NO_VENTILATION" in checked
        assert "HABITABLE_ROOM_WINDOW" in checked

    def test_rooms_have_ventilation_fields(self, client, basic_payload):
        resp = client.post("/api/v1/layouts/generate", json=basic_payload)
        assert resp.status_code == 200
        data = resp.json()
        cand = data["candidates"][0]
        for room in cand["rooms"]:
            assert "has_ventilation" in room
            assert "mechanical_ventilation" in room
            assert "ventilation_shaft" in room
            assert isinstance(room["has_ventilation"], bool)
