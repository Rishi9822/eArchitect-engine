"""
Unit tests for Priority 1: Door Placement Graph & Architectural Logic.
"""
import pytest
from shapely.geometry import Polygon
from app.layout.doors import (
    generate_doors,
    classify_door_edge,
    get_door_width,
)
from app.config import (
    DOOR_ADJACENCY_FORBIDDEN,
    DOOR_ADJACENCY_PREFERRED,
    DOOR_ADJACENCY_ACCEPTABLE,
    DOOR_ADJACENCY_DISCOURAGED,
    DOOR_WALL_CLEARANCE_M,
)


def test_classify_forbidden_pairs():
    assert classify_door_edge("toilet", "toilet") == float("inf")
    assert classify_door_edge("toilet", "kitchen") == float("inf")
    assert classify_door_edge("toilet", "dining") == float("inf")
    assert classify_door_edge("bedroom", "bedroom") == float("inf")
    assert classify_door_edge("bedroom", "kitchen") == float("inf")
    assert classify_door_edge("parking", "toilet") == float("inf")
    assert classify_door_edge("parking", "bedroom") == float("inf")


def test_classify_preferred_pairs():
    assert classify_door_edge("living", "dining") == 1.0
    assert classify_door_edge("living", "corridor") == 1.0
    assert classify_door_edge("dining", "kitchen") == 1.0
    assert classify_door_edge("corridor", "bedroom") == 1.0
    assert classify_door_edge("corridor", "toilet") == 1.0


def test_living_bedroom_corridor_awareness():
    # Without corridor: acceptable (3.0)
    assert classify_door_edge("living", "bedroom", has_corridor=False) == 3.0
    # With corridor: discouraged (8.0)
    assert classify_door_edge("living", "bedroom", has_corridor=True) == 8.0


def test_door_widths():
    assert get_door_width("toilet", "living") == 0.75
    assert get_door_width("bathroom", "bedroom") == 0.75
    assert get_door_width("living", "dining") == 0.90
    assert get_door_width("bedroom", "living") == 0.90
    assert get_door_width("parking", "kitchen") == 0.90


def test_forbidden_doors_never_placed_between_toilets():
    # Two adjacent toilets
    toilet_0 = Polygon([(0, 0), (3, 0), (3, 3), (0, 3)])
    toilet_1 = Polygon([(3, 0), (6, 0), (6, 3), (3, 3)])
    living_0 = Polygon([(0, 3), (6, 3), (6, 8), (0, 8)])

    polys = {"toilet_0": toilet_0, "toilet_1": toilet_1, "living_0": living_0}
    types = {"toilet_0": "toilet", "toilet_1": "toilet", "living_0": "living"}

    doors = generate_doors(polys, types, entrance_room_id="living_0")

    # Each toilet should connect to living, NEVER to each other
    connected_pairs = {tuple(sorted([d["from_room"], d["to_room"]])) for d in doors}
    assert ("toilet_0", "toilet_1") not in connected_pairs
    assert ("living_0", "toilet_0") in connected_pairs
    assert ("living_0", "toilet_1") in connected_pairs


def test_toilet_isolated_by_forbidden_edges_reported():
    # Toilet adjacent ONLY to kitchen and another toilet
    toilet_0 = Polygon([(0, 0), (3, 0), (3, 3), (0, 3)])
    kitchen_0 = Polygon([(3, 0), (6, 0), (6, 3), (3, 3)])

    polys = {"toilet_0": toilet_0, "kitchen_0": kitchen_0}
    types = {"toilet_0": "toilet", "kitchen_0": "kitchen"}

    doors = generate_doors(polys, types)
    # Zero doors placed because toilet <-> kitchen is forbidden
    assert len(doors) == 0
    assert "toilet_0" in doors.unreachable_rooms or "kitchen_0" in doors.unreachable_rooms


def test_door_clearance_filtering():
    # Wall is 1.0m, but living <-> bedroom needs 0.9 + 0.3 = 1.2m
    room_a = Polygon([(0, 0), (1.0, 0), (1.0, 5), (0, 5)])
    room_b = Polygon([(1.0, 0), (2.0, 0), (2.0, 1.0), (1.0, 1.0)])  # shares 1.0m wall

    polys = {"living_0": room_a, "bedroom_0": room_b}
    types = {"living_0": "living", "bedroom_0": "bedroom"}

    doors = generate_doors(polys, types)
    assert len(doors) == 0  # 1.0m wall < 1.2m clearance threshold
