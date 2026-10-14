"""
Tests for Priority 9: Irregular / Non-Orthogonal Plot Handling.

Verifies:
1. Polygon internal angles and orthogonality classification.
2. Inscribed circle diameter calculation via Shapely polylabel.
3. MIN_ROOM_INSCRIBED_CIRCLE hard constraint for habitable rooms (diameter >= 2.4m).
4. Acute corner handling (<60°): clipping acute slivers and classifying as storage nooks.
5. BSP split lines along plot edge bearings.
6. End-to-end pipeline execution on irregular concave plot and pentagonal plot.
7. Verification of room output fields: is_orthogonal, min_internal_angle_deg, inscribed_circle_diameter_m.
"""
import json
import pytest
from shapely.geometry import Polygon, box

from app.geometry.polygon_utils import (
    get_polygon_internal_angles,
    is_polygon_orthogonal,
    min_polygon_internal_angle,
    compute_inscribed_circle_diameter,
    get_polygon_edge_bearings,
    clip_acute_corners,
    build_split_line,
    split_polygon,
)
from app.layout.bsp import classify_dead_space
from app.layout.constraints import check_min_room_inscribed_circle, HARD_CONSTRAINTS
from app.services.layout_service import generate_layout_response
from app.models.input_models import GenerateLayoutRequest


class TestPriority9GeometryHelpers:
    """Test geometry functions for internal angles, orthogonality, and inscribed circles."""

    def test_rectangle_orthogonality(self):
        rect = Polygon([(0, 0), (10, 0), (10, 6), (0, 6)])
        angles = get_polygon_internal_angles(rect)
        assert len(angles) == 4
        for a in angles:
            assert abs(a - 90.0) < 0.1
        assert is_polygon_orthogonal(rect) is True
        assert min_polygon_internal_angle(rect) == 90.0

    def test_l_shape_orthogonality(self):
        l_shape = Polygon([(0, 0), (10, 0), (10, 5), (5, 5), (5, 10), (0, 10)])
        assert is_polygon_orthogonal(l_shape) is True
        assert min_polygon_internal_angle(l_shape) == 90.0

    def test_non_orthogonal_polygon(self):
        # Trapezoid with 60° and 120° angles
        trapezoid = Polygon([(0, 0), (10, 0), (8, 4), (2, 4)])
        assert is_polygon_orthogonal(trapezoid) is False
        min_ang = min_polygon_internal_angle(trapezoid)
        assert min_ang < 89.0

    def test_inscribed_circle_diameter(self):
        # 4m x 8m rectangle -> diameter should be 4.0m
        r4x8 = box(0, 0, 8, 4)
        dia = compute_inscribed_circle_diameter(r4x8)
        assert abs(dia - 4.0) < 0.05

        # 3m x 3m square -> diameter should be 3.0m
        r3x3 = box(0, 0, 3, 3)
        dia3 = compute_inscribed_circle_diameter(r3x3)
        assert abs(dia3 - 3.0) < 0.05

    def test_get_polygon_edge_bearings(self):
        # Rectangle has no diagonal bearings
        rect = Polygon([(0, 0), (10, 0), (10, 6), (0, 6)])
        assert get_polygon_edge_bearings(rect) == []

        # Polygon with a 45° diagonal edge
        poly_diag = Polygon([(0, 0), (10, 0), (10, 5), (5, 10), (0, 10)])
        bearings = get_polygon_edge_bearings(poly_diag)
        assert len(bearings) > 0


class TestPriority9AcuteCornerHandling:
    """Test clipping of acute corners (<60°) and conversion to storage nooks."""

    def test_clip_acute_corner_triangle(self):
        # Sharp triangle with 45° corners at (0,0) and (6,6)
        poly = Polygon([(0, 0), (6, 0), (6, 6)])
        clipped, slivers = clip_acute_corners(poly, min_angle_deg=60.0)
        assert len(slivers) >= 1
        assert clipped.area < poly.area

        # Verify slivers are classified as storage nooks in dead space
        for s in slivers:
            cat = classify_dead_space(s)
            assert cat == "storage"

    def test_classify_acute_triangle_storage(self):
        # Triangle with an acute angle of 30°
        tri_acute = Polygon([(0, 0), (6, 0), (3, 1)])
        cat = classify_dead_space(tri_acute)
        assert cat == "storage"


class TestPriority9SplitLineBearings:
    """Test BSP splitting along arbitrary bearing angles."""

    def test_bearing_split_diagonal(self):
        square = box(0, 0, 10, 10)
        # Split along 45 degree bearing
        left, right = split_polygon(square, axis=45.0, ratio=0.5)
        assert left is not None and right is not None
        assert abs(left.area - 50.0) < 1.0
        assert abs(right.area - 50.0) < 1.0


class TestPriority9InscribedCircleConstraint:
    """Test MIN_ROOM_INSCRIBED_CIRCLE hard gate constraint."""

    def test_constraint_registered_in_hard_constraints(self):
        assert "MIN_ROOM_INSCRIBED_CIRCLE" in HARD_CONSTRAINTS

    def test_habitable_room_narrow_fails(self):
        # Narrow bedroom: 1.5m x 10m -> inscribed circle diameter is ~1.5m (< 2.4m)
        room_polys = {"bedroom_0": box(0, 0, 10, 1.5)}
        room_types = {"bedroom_0": "bedroom"}
        errors = check_min_room_inscribed_circle(room_polys, room_types, min_diameter_m=2.4)
        assert len(errors) == 1
        assert errors[0]["code"] == "MIN_ROOM_INSCRIBED_CIRCLE"
        assert errors[0]["details"]["inscribed_circle_diameter_m"] < 2.4

    def test_habitable_room_adequate_passes(self):
        # Adequate bedroom: 3.5m x 4.0m -> inscribed circle diameter is 3.5m (>= 2.4m)
        room_polys = {"bedroom_0": box(0, 0, 4.0, 3.5)}
        room_types = {"bedroom_0": "bedroom"}
        errors = check_min_room_inscribed_circle(room_polys, room_types, min_diameter_m=2.4)
        assert len(errors) == 0

    def test_non_habitable_room_exempt(self):
        # Toilet: 1.2m x 2.0m -> toilet is not habitable, should not fail MIN_ROOM_INSCRIBED_CIRCLE
        room_polys = {"toilet_0": box(0, 0, 2.0, 1.2)}
        room_types = {"toilet_0": "toilet"}
        errors = check_min_room_inscribed_circle(room_polys, room_types, min_diameter_m=2.4)
        assert len(errors) == 0


class TestPriority9PipelineIntegration:
    """End-to-end integration test with irregular concave and pentagonal plots."""

    def test_irregular_concave_plot_pipeline(self):
        with open("samples/irregular_concave.json", "r") as f:
            data = json.load(f)
        req = GenerateLayoutRequest(**data)
        response = generate_layout_response(req)

        assert len(response["candidates"]) > 0
        best_cand = response["candidates"][0]

        # Verify MIN_ROOM_INSCRIBED_CIRCLE in constraints_checked
        assert "MIN_ROOM_INSCRIBED_CIRCLE" in best_cand["validation"]["constraints_checked"]

        # Verify room output fields
        for room in best_cand["rooms"]:
            assert "is_orthogonal" in room
            assert isinstance(room["is_orthogonal"], bool)
            assert "min_internal_angle_deg" in room
            assert isinstance(room["min_internal_angle_deg"], (int, float))
            assert "inscribed_circle_diameter_m" in room
            assert isinstance(room["inscribed_circle_diameter_m"], (int, float))
            assert room["inscribed_circle_diameter_m"] >= 0.0

    def test_pentagonal_plot_pipeline(self):
        pentagon_payload = {
            "plot": {
                "points": [
                    {"x": 0, "y": 0},
                    {"x": 16, "y": 0},
                    {"x": 16, "y": 14},
                    {"x": 8, "y": 18},
                    {"x": 0, "y": 14},
                ],
                "facing": "north",
                "road_side": "front",
                "setback": 1.5,
            },
            "rooms": [
                {"type": "living", "count": 1, "min_area": 140},
                {"type": "dining", "count": 1, "min_area": 80},
                {"type": "kitchen", "count": 1, "min_area": 70},
                {"type": "bedroom", "count": 1, "min_area": 110},
                {"type": "toilet", "count": 1, "min_area": 35},
            ],
            "entrance": {"side": "front", "width": 1.2},
            "preferences": {"parking": True},
            "candidate_count": 2,
            "seed": 42,
        }
        req = GenerateLayoutRequest(**pentagon_payload)
        response = generate_layout_response(req)

        assert len(response["candidates"]) > 0
        cand = response["candidates"][0]
        assert "MIN_ROOM_INSCRIBED_CIRCLE" in cand["validation"]["constraints_checked"]
        for room in cand["rooms"]:
            assert "is_orthogonal" in room
            assert "min_internal_angle_deg" in room
            assert "inscribed_circle_diameter_m" in room
