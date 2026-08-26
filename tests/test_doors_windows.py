"""
Tests for door and window generation.
"""
import pytest
from shapely.geometry import Polygon
from app.layout.doors import generate_doors
from app.layout.windows import generate_windows


class TestDoors:
    def _make_adjacent_rooms(self):
        room_a = Polygon([(0, 0), (6, 0), (6, 8), (0, 8)])
        room_b = Polygon([(6, 0), (12, 0), (12, 8), (6, 8)])
        return {"living_0": room_a, "bedroom_0": room_b}, \
               {"living_0": "living", "bedroom_0": "bedroom"}

    def test_door_generated_for_adjacent(self):
        polys, types = self._make_adjacent_rooms()
        doors = generate_doors(polys, types)
        assert len(doors) >= 1

    def test_door_has_required_fields(self):
        polys, types = self._make_adjacent_rooms()
        doors = generate_doors(polys, types)
        for d in doors:
            assert "id" in d
            assert "type" in d
            assert "width" in d
            assert "position" in d
            assert "from_room" in d
            assert "to_room" in d

    def test_no_door_for_non_adjacent(self):
        room_a = Polygon([(0, 0), (5, 0), (5, 5), (0, 5)])
        room_b = Polygon([(10, 10), (15, 10), (15, 15), (10, 15)])
        polys = {"room_a": room_a, "room_b": room_b}
        types = {"room_a": "living", "room_b": "bedroom"}
        doors = generate_doors(polys, types)
        assert len(doors) == 0


class TestWindows:
    def test_windows_on_exterior(self):
        room = Polygon([(0, 0), (6, 0), (6, 8), (0, 8)])
        boundary = Polygon([(0, 0), (12, 0), (12, 8), (0, 8)])
        polys = {"living_0": room}
        types = {"living_0": "living"}
        prefs = {"natural_light_priority": True, "ventilation_priority": True}
        windows = generate_windows(polys, types, boundary, prefs)
        assert len(windows) >= 1

    def test_window_has_required_fields(self):
        room = Polygon([(0, 0), (6, 0), (6, 8), (0, 8)])
        boundary = Polygon([(0, 0), (12, 0), (12, 8), (0, 8)])
        polys = {"bedroom_0": room}
        types = {"bedroom_0": "bedroom"}
        prefs = {"natural_light_priority": False, "ventilation_priority": False}
        windows = generate_windows(polys, types, boundary, prefs)
        for w in windows:
            assert "id" in w
            assert "room_id" in w
            assert "width" in w
            assert "position" in w
            assert "type" in w

    def test_no_window_for_store(self):
        room = Polygon([(0, 0), (4, 0), (4, 5), (0, 5)])
        boundary = Polygon([(0, 0), (10, 0), (10, 5), (0, 5)])
        polys = {"store_0": room}
        types = {"store_0": "store"}
        prefs = {}
        windows = generate_windows(polys, types, boundary, prefs)
        assert len(windows) == 0
