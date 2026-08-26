"""
Tests for wall extraction, cleanup, and pairwise boundary extraction.
"""
import math
import pytest
from shapely.geometry import Polygon, LineString
from app.walls.extractor import extract_wall_segments
from app.config import MIN_WALL_LENGTH


class TestWallExtraction:
    def _make_simple_rooms(self):
        """Two adjacent rectangular rooms sharing a wall."""
        room_a = Polygon([(0, 0), (5, 0), (5, 8), (0, 8)])
        room_b = Polygon([(5, 0), (12, 0), (12, 8), (5, 8)])
        boundary = Polygon([(0, 0), (12, 0), (12, 8), (0, 8)])
        return [room_a, room_b], ["living_0", "bedroom_0"], boundary

    def _make_t_junction_rooms(self):
        """
        Three rooms in a T-junction layout:
        room_a (bottom): [0,0] to [10,5]
        room_b (top-left): [0,5] to [4,10]
        room_c (top-right): [4,5] to [10,10]
        """
        room_a = Polygon([(0, 0), (10, 0), (10, 5), (0, 5)])
        room_b = Polygon([(0, 5), (4, 5), (4, 10), (0, 10)])
        room_c = Polygon([(4, 5), (10, 5), (10, 10), (4, 10)])
        boundary = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        return [room_a, room_b, room_c], ["bedroom_0", "kitchen_0", "toilet_0"], boundary

    def test_basic_extraction(self):
        polys, ids, boundary = self._make_simple_rooms()
        walls = extract_wall_segments(polys, ids, boundary, boundary)
        assert len(walls) > 0

    def test_wall_ids_assigned(self):
        polys, ids, boundary = self._make_simple_rooms()
        walls = extract_wall_segments(polys, ids, boundary, boundary)
        for w in walls:
            assert "id" in w
            assert w["id"].startswith("W")

    def test_wall_types(self):
        polys, ids, boundary = self._make_simple_rooms()
        walls = extract_wall_segments(polys, ids, boundary, boundary)
        types = {w["type"] for w in walls}
        assert "exterior" in types
        assert "interior" in types

    def test_no_tiny_walls(self):
        """All returned walls should meet minimum length."""
        polys, ids, boundary = self._make_simple_rooms()
        walls = extract_wall_segments(polys, ids, boundary, boundary)
        for w in walls:
            assert w["length"] >= MIN_WALL_LENGTH, (
                f"Wall {w['id']} has length {w['length']} < {MIN_WALL_LENGTH}"
            )

    def test_room_relationships(self):
        """Interior walls should have room_a and room_b."""
        polys, ids, boundary = self._make_simple_rooms()
        walls = extract_wall_segments(polys, ids, boundary, boundary)
        interior = [w for w in walls if w["type"] == "interior"]
        for w in interior:
            assert w.get("room_a") is not None and w.get("room_b") is not None

    def test_exterior_walls_null_room_b(self):
        """Exterior walls should have room_b = None."""
        polys, ids, boundary = self._make_simple_rooms()
        walls = extract_wall_segments(polys, ids, boundary, boundary)
        exterior = [w for w in walls if w["type"] == "exterior"]
        for w in exterior:
            assert w.get("room_b") is None

    def test_orientation_present(self):
        polys, ids, boundary = self._make_simple_rooms()
        walls = extract_wall_segments(polys, ids, boundary, boundary)
        for w in walls:
            assert w.get("orientation") in ("horizontal", "vertical", "diagonal")

    def test_bearing_in_range(self):
        polys, ids, boundary = self._make_simple_rooms()
        walls = extract_wall_segments(polys, ids, boundary, boundary)
        for w in walls:
            assert 0 <= w.get("bearing_deg", 0) <= 360

    # ── Test A: Exact duplicate prevention ───────────────────────────
    def test_exact_duplicate_prevention(self):
        polys, ids, boundary = self._make_t_junction_rooms()
        walls = extract_wall_segments(polys, ids, boundary, boundary)
        interior = [w for w in walls if w["type"] == "interior"]

        # Check that each unordered pair of rooms appears at most once for a contiguous segment
        pairs = [frozenset([w["room_a"], w["room_b"]]) for w in interior]
        # In T-junction, bedroom_0 ↔ kitchen_0 and bedroom_0 ↔ toilet_0 and kitchen_0 ↔ toilet_0
        assert len(pairs) == len(set(pairs))

    # ── Test B: Reverse relationship prevention ──────────────────────
    def test_reverse_relationship_prevention(self):
        polys, ids, boundary = self._make_simple_rooms()
        walls = extract_wall_segments(polys, ids, boundary, boundary)
        interior = [w for w in walls if w["type"] == "interior"]

        assert len(interior) == 1
        w = interior[0]
        assert set([w["room_a"], w["room_b"]]) == {"living_0", "bedroom_0"}

    # ── Test C: Partial overlap prevention ───────────────────────────
    def test_partial_overlap_prevention(self):
        polys, ids, boundary = self._make_t_junction_rooms()
        walls = extract_wall_segments(polys, ids, boundary, boundary)
        interior = [w for w in walls if w["type"] == "interior"]

        # For every pair of interior walls, check that their 1D intersection is empty (or a point)
        for i in range(len(interior)):
            line_a = LineString([
                (interior[i]["start"]["x"], interior[i]["start"]["y"]),
                (interior[i]["end"]["x"], interior[i]["end"]["y"]),
            ])
            for j in range(i + 1, len(interior)):
                line_b = LineString([
                    (interior[j]["start"]["x"], interior[j]["start"]["y"]),
                    (interior[j]["end"]["x"], interior[j]["end"]["y"]),
                ])
                inters = line_a.intersection(line_b)
                # Overlap must not be a LineString of positive length
                if isinstance(inters, LineString):
                    assert inters.length < 1e-4, (
                        f"Walls {interior[i]['id']} and {interior[j]['id']} overlap by {inters.length}m"
                    )

    # ── Test D: Corner touching produces no interior wall ────────────
    def test_corner_touching_no_interior_wall(self):
        """Two rooms touching only at point (5, 5)."""
        room_a = Polygon([(0, 0), (5, 0), (5, 5), (0, 5)])
        room_b = Polygon([(5, 5), (10, 5), (10, 10), (5, 10)])
        boundary = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        walls = extract_wall_segments([room_a, room_b], ["room_a", "room_b"], boundary, boundary)
        interior = [w for w in walls if w["type"] == "interior"]
        assert len(interior) == 0

    # ── Test E: Shared boundary length accuracy ──────────────────────
    def test_shared_boundary_length_exact(self):
        room_a = Polygon([(0, 0), (6, 0), (6, 8), (0, 8)])
        room_b = Polygon([(6, 0), (12, 0), (12, 8), (6, 8)])
        boundary = Polygon([(0, 0), (12, 0), (12, 8), (0, 8)])
        walls = extract_wall_segments([room_a, room_b], ["room_a", "room_b"], boundary, boundary)
        interior = [w for w in walls if w["type"] == "interior"]
        assert len(interior) == 1
        assert abs(interior[0]["length"] - 8.0) < 1e-3

    # ── Test F: Length integrity with coordinates ────────────────────
    def test_length_integrity_with_coordinates(self):
        polys, ids, boundary = self._make_t_junction_rooms()
        walls = extract_wall_segments(polys, ids, boundary, boundary)
        for w in walls:
            dx = w["end"]["x"] - w["start"]["x"]
            dy = w["end"]["y"] - w["start"]["y"]
            coord_dist = math.hypot(dx, dy)
            assert abs(w["length"] - coord_dist) <= 1e-3, (
                f"Wall {w['id']} reported length {w['length']} != coord distance {coord_dist}"
            )

    # ── Test G: Room relationship integrity ──────────────────────────
    def test_room_relationship_integrity(self):
        polys, ids, boundary = self._make_t_junction_rooms()
        room_dict = dict(zip(ids, polys))
        walls = extract_wall_segments(polys, ids, boundary, boundary)
        interior = [w for w in walls if w["type"] == "interior"]

        for w in interior:
            poly_a = room_dict[w["room_a"]]
            poly_b = room_dict[w["room_b"]]
            shared = poly_a.boundary.intersection(poly_b.boundary)
            wall_line = LineString([(w["start"]["x"], w["start"]["y"]), (w["end"]["x"], w["end"]["y"])])
            # The wall line midpoint must lie on the shared boundary
            mid = wall_line.interpolate(0.5, normalized=True)
            assert shared.distance(mid) < 0.05
