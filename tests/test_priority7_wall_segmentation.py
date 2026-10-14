"""
Tests for Priority 7: Exterior Wall Segmentation at Room Boundaries.

Verifies:
- Exterior walls are split at internal room boundary intersections
- No exterior segment spans multiple rooms
- Collinear merging only applies within the same room
- Perimeter conservation (sum of exterior wall lengths ≈ perimeter)
"""
import math
import pytest
from shapely.geometry import Polygon, LineString
from app.walls.extractor import (
    extract_wall_segments,
    _collect_interior_split_points,
    _split_segment_at_points,
    _assign_room_to_segment,
    _are_collinear,
)
from app.config import MIN_WALL_LENGTH


class TestExteriorWallSegmentation:
    """Core Priority 7 tests: exterior wall splitting at room boundaries."""

    def _make_two_rooms_on_one_side(self):
        """
        Two rooms sharing an exterior edge:
        room_a (left):  [0,0]–[6,0]–[6,10]–[0,10]
        room_b (right): [6,0]–[12,0]–[12,10]–[6,10]
        boundary:       [0,0]–[12,0]–[12,10]–[0,10]

        The bottom exterior edge (y=0) spans both rooms and should be split
        at x=6 into two segments, one per room.
        """
        room_a = Polygon([(0, 0), (6, 0), (6, 10), (0, 10)])
        room_b = Polygon([(6, 0), (12, 0), (12, 10), (6, 10)])
        boundary = Polygon([(0, 0), (12, 0), (12, 10), (0, 10)])
        return [room_a, room_b], ["living_0", "bedroom_0"], boundary

    def _make_three_rooms_on_one_side(self):
        """
        Three rooms sharing the bottom exterior edge (y=0):
        room_a: [0,0]–[4,0]–[4,10]–[0,10]
        room_b: [4,0]–[8,0]–[8,10]–[4,10]
        room_c: [8,0]–[12,0]–[12,10]–[8,10]
        boundary: [0,0]–[12,0]–[12,10]–[0,10]
        """
        room_a = Polygon([(0, 0), (4, 0), (4, 10), (0, 10)])
        room_b = Polygon([(4, 0), (8, 0), (8, 10), (4, 10)])
        room_c = Polygon([(8, 0), (12, 0), (12, 10), (8, 10)])
        boundary = Polygon([(0, 0), (12, 0), (12, 10), (0, 10)])
        return [room_a, room_b, room_c], ["living_0", "bedroom_0", "kitchen_0"], boundary

    def test_exterior_segments_split_at_room_boundary(self):
        """
        Two rooms sharing the bottom edge: the bottom exterior should be
        split into two separate segments, each assigned to its own room.
        """
        polys, ids, boundary = self._make_two_rooms_on_one_side()
        walls = extract_wall_segments(polys, ids, boundary, boundary)
        exterior = [w for w in walls if w["type"] == "exterior"]

        # The bottom edge (y=0) should NOT be a single 12m segment
        bottom = [w for w in exterior if
                  abs(w["start"]["y"]) < 0.1 and abs(w["end"]["y"]) < 0.1]

        # Should be at least 2 bottom segments (one per room)
        assert len(bottom) >= 2, (
            f"Expected >=2 bottom exterior segments but got {len(bottom)}: {bottom}"
        )

        # Each should be attributed to a different room
        bottom_rooms = {w["room_a"] for w in bottom}
        assert len(bottom_rooms) == 2, (
            f"Expected 2 different rooms on bottom edge, got {bottom_rooms}"
        )
        assert bottom_rooms == {"living_0", "bedroom_0"}

    def test_no_exterior_segment_spans_multiple_rooms(self):
        """No single exterior segment should be attributed to more than one room."""
        polys, ids, boundary = self._make_two_rooms_on_one_side()
        walls = extract_wall_segments(polys, ids, boundary, boundary)
        exterior = [w for w in walls if w["type"] == "exterior"]

        for w in exterior:
            assert w["room_b"] is None, f"Exterior wall {w['id']} has room_b set"
            assert w["room_a"] is not None, f"Exterior wall {w['id']} has no room_a"

    def test_collinear_merge_blocked_across_rooms(self):
        """
        Two collinear exterior segments belonging to different rooms
        must NOT be merged.
        """
        seg_a = {
            "start": {"x": 0.0, "y": 0.0},
            "end": {"x": 6.0, "y": 0.0},
            "type": "exterior",
            "room_a": "living_0",
        }
        seg_b = {
            "start": {"x": 6.0, "y": 0.0},
            "end": {"x": 12.0, "y": 0.0},
            "type": "exterior",
            "room_a": "bedroom_0",
        }
        assert not _are_collinear(seg_a, seg_b), (
            "Collinear segments from different rooms should not be merged"
        )

    def test_collinear_merge_allowed_within_same_room(self):
        """
        Two collinear exterior segments belonging to the SAME room
        can still be merged.
        """
        seg_a = {
            "start": {"x": 0.0, "y": 0.0},
            "end": {"x": 3.0, "y": 0.0},
            "type": "exterior",
            "room_a": "living_0",
        }
        seg_b = {
            "start": {"x": 3.0, "y": 0.0},
            "end": {"x": 6.0, "y": 0.0},
            "type": "exterior",
            "room_a": "living_0",
        }
        assert _are_collinear(seg_a, seg_b), (
            "Collinear segments from the same room should still merge"
        )

    def test_three_rooms_split_correctly(self):
        """Three rooms on one exterior edge produce three distinct segments."""
        polys, ids, boundary = self._make_three_rooms_on_one_side()
        walls = extract_wall_segments(polys, ids, boundary, boundary)
        exterior = [w for w in walls if w["type"] == "exterior"]

        bottom = [w for w in exterior if
                  abs(w["start"]["y"]) < 0.1 and abs(w["end"]["y"]) < 0.1]

        assert len(bottom) >= 3, (
            f"Expected >=3 bottom exterior segments for 3 rooms, got {len(bottom)}"
        )

        bottom_rooms = {w["room_a"] for w in bottom}
        assert bottom_rooms == {"living_0", "bedroom_0", "kitchen_0"}


class TestPerimeterConservation:
    """Verify that sum(exterior wall lengths) ≈ buildable perimeter."""

    def test_simple_rectangle_perimeter(self):
        """Two rooms in a rectangle: total exterior = 2*(12+10) = 44m."""
        room_a = Polygon([(0, 0), (6, 0), (6, 10), (0, 10)])
        room_b = Polygon([(6, 0), (12, 0), (12, 10), (6, 10)])
        boundary = Polygon([(0, 0), (12, 0), (12, 10), (0, 10)])

        walls = extract_wall_segments([room_a, room_b], ["a", "b"], boundary, boundary)
        exterior = [w for w in walls if w["type"] == "exterior"]

        ext_total = sum(w["length"] for w in exterior)
        expected_perimeter = boundary.length  # 44m

        assert abs(ext_total - expected_perimeter) < 0.5, (
            f"Exterior wall sum {ext_total:.4f} m != perimeter {expected_perimeter:.4f} m "
            f"(delta={abs(ext_total - expected_perimeter):.4f})"
        )

    def test_t_junction_perimeter(self):
        """T-junction with 3 rooms should still conserve perimeter."""
        room_a = Polygon([(0, 0), (10, 0), (10, 5), (0, 5)])
        room_b = Polygon([(0, 5), (4, 5), (4, 10), (0, 10)])
        room_c = Polygon([(4, 5), (10, 5), (10, 10), (4, 10)])
        boundary = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])

        walls = extract_wall_segments(
            [room_a, room_b, room_c],
            ["bedroom_0", "kitchen_0", "toilet_0"],
            boundary, boundary,
        )
        exterior = [w for w in walls if w["type"] == "exterior"]

        ext_total = sum(w["length"] for w in exterior)
        expected_perimeter = boundary.length  # 40m

        assert abs(ext_total - expected_perimeter) < 0.5, (
            f"Exterior wall sum {ext_total:.4f} m != perimeter {expected_perimeter:.4f} m"
        )


class TestSplitPoints:
    """Tests for internal helper functions."""

    def test_collect_split_points(self):
        """Room corners on the perimeter should be collected as split points."""
        room_a = Polygon([(0, 0), (6, 0), (6, 10), (0, 10)])
        room_b = Polygon([(6, 0), (12, 0), (12, 10), (6, 10)])
        boundary = Polygon([(0, 0), (12, 0), (12, 10), (0, 10)])

        pts = _collect_interior_split_points([room_a, room_b], boundary.boundary)
        # (6, 0) and (6, 10) should be among the split points
        pt_coords = {(round(p.x, 2), round(p.y, 2)) for p in pts}
        assert (6.0, 0.0) in pt_coords
        assert (6.0, 10.0) in pt_coords

    def test_split_segment_at_midpoint(self):
        """Splitting a 12m segment at x=6 should produce two 6m segments."""
        seg = LineString([(0, 0), (12, 0)])
        from shapely.geometry import Point as ShapelyPoint
        pts = [ShapelyPoint(6, 0)]
        result = _split_segment_at_points(seg, pts)
        assert len(result) == 2
        for sub in result:
            assert abs(sub.length - 6.0) < 0.1

    def test_assign_room_to_segment(self):
        """Segment on room_a's boundary should be assigned to room_a."""
        room_a = Polygon([(0, 0), (6, 0), (6, 10), (0, 10)])
        room_b = Polygon([(6, 0), (12, 0), (12, 10), (6, 10)])
        seg = LineString([(1, 0), (5, 0)])
        rid = _assign_room_to_segment(seg, [room_a, room_b], ["living_0", "bedroom_0"])
        assert rid == "living_0"

    def test_assign_room_right_side(self):
        """Segment on room_b's boundary should be assigned to room_b."""
        room_a = Polygon([(0, 0), (6, 0), (6, 10), (0, 10)])
        room_b = Polygon([(6, 0), (12, 0), (12, 10), (6, 10)])
        seg = LineString([(7, 0), (11, 0)])
        rid = _assign_room_to_segment(seg, [room_a, room_b], ["living_0", "bedroom_0"])
        assert rid == "bedroom_0"


class TestExistingTestsStillPass:
    """Ensure all existing wall test scenarios are unbroken."""

    def test_basic_extraction_still_works(self):
        room_a = Polygon([(0, 0), (5, 0), (5, 8), (0, 8)])
        room_b = Polygon([(5, 0), (12, 0), (12, 8), (5, 8)])
        boundary = Polygon([(0, 0), (12, 0), (12, 8), (0, 8)])
        walls = extract_wall_segments([room_a, room_b], ["living_0", "bedroom_0"], boundary, boundary)
        assert len(walls) > 0

    def test_interior_relationships_preserved(self):
        room_a = Polygon([(0, 0), (5, 0), (5, 8), (0, 8)])
        room_b = Polygon([(5, 0), (12, 0), (12, 8), (5, 8)])
        boundary = Polygon([(0, 0), (12, 0), (12, 8), (0, 8)])
        walls = extract_wall_segments([room_a, room_b], ["living_0", "bedroom_0"], boundary, boundary)
        interior = [w for w in walls if w["type"] == "interior"]
        assert len(interior) == 1
        w = interior[0]
        assert set([w["room_a"], w["room_b"]]) == {"living_0", "bedroom_0"}

    def test_corner_touching_still_no_interior(self):
        room_a = Polygon([(0, 0), (5, 0), (5, 5), (0, 5)])
        room_b = Polygon([(5, 5), (10, 5), (10, 10), (5, 10)])
        boundary = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        walls = extract_wall_segments([room_a, room_b], ["room_a", "room_b"], boundary, boundary)
        interior = [w for w in walls if w["type"] == "interior"]
        assert len(interior) == 0
