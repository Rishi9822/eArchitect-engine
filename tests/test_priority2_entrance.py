"""
Unit tests for Priority 2: Entrance Placement — Room-Driven Selection.

Tests verify:
  - Eligible room types (foyer > living > corridor > dining) are selected
  - Ineligible room types (bedroom, toilet, kitchen, parking, etc.) are never chosen
  - Priority ordering works (foyer beats living beats corridor beats dining)
  - Longer shared boundary wins within the same priority tier
  - ENTRANCE_NO_ELIGIBLE_ROOM is emitted when no eligible room touches road side
"""
import pytest
from shapely.geometry import Polygon

from app.layout.entrance import (
    find_entrance_wall,
    ENTRANCE_ROOM_PRIORITY,
    ENTRANCE_INELIGIBLE_TYPES,
    _road_side_boundary,
    _shared_road_length,
)


# ─────────────────────────────────────────────
# HELPER — simple 10×10 buildable square facing north
# ─────────────────────────────────────────────

def _buildable() -> Polygon:
    """10 m × 10 m square; front (north-facing road) is the TOP edge y=10."""
    return Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])


# ─────────────────────────────────────────────
# Constant tables
# ─────────────────────────────────────────────

def test_entrance_priority_table():
    assert ENTRANCE_ROOM_PRIORITY["foyer"] == 1
    assert ENTRANCE_ROOM_PRIORITY["living"] == 2
    assert ENTRANCE_ROOM_PRIORITY["corridor"] == 3
    assert ENTRANCE_ROOM_PRIORITY["dining"] == 4


def test_ineligible_types_set():
    for t in ("bedroom", "master_bedroom", "toilet", "bathroom",
              "kitchen", "parking", "store", "utility", "dressing", "study"):
        assert t in ENTRANCE_INELIGIBLE_TYPES


# ─────────────────────────────────────────────
# _road_side_boundary
# ─────────────────────────────────────────────

def test_road_boundary_north_facing_front():
    inner = _buildable()
    road = _road_side_boundary(inner, side="front", facing="north")
    assert road is not None
    mid = road.interpolate(0.5, normalized=True)
    assert mid.y > 8.0


def test_road_boundary_back_north_facing():
    inner = _buildable()
    road = _road_side_boundary(inner, side="back", facing="north")
    assert road is not None


# ─────────────────────────────────────────────
# Eligibility filtering
# ─────────────────────────────────────────────

def _make_rooms_with_road_contact(room_type):
    inner = _buildable()
    room_poly = Polygon([(0, 5), (10, 5), (10, 10), (0, 10)])
    return inner, {"R001": room_poly}, {"R001": room_type}


def test_living_room_touching_road_is_selected():
    inner, rp, rt = _make_rooms_with_road_contact("living")
    result = find_entrance_wall(inner, rp, rt, side="front", facing="north")
    assert result is not None
    assert result["room_id"] == "R001"


def test_foyer_touching_road_is_selected():
    inner, rp, rt = _make_rooms_with_road_contact("foyer")
    result = find_entrance_wall(inner, rp, rt, side="front", facing="north")
    assert result is not None
    assert result["room_id"] == "R001"


def test_dining_touching_road_is_selected():
    inner, rp, rt = _make_rooms_with_road_contact("dining")
    result = find_entrance_wall(inner, rp, rt, side="front", facing="north")
    assert result is not None
    assert result["room_id"] == "R001"


def test_corridor_touching_road_is_selected():
    inner, rp, rt = _make_rooms_with_road_contact("corridor")
    result = find_entrance_wall(inner, rp, rt, side="front", facing="north")
    assert result is not None
    assert result["room_id"] == "R001"


def test_bedroom_touching_road_is_rejected():
    inner, rp, rt = _make_rooms_with_road_contact("bedroom")
    assert find_entrance_wall(inner, rp, rt, side="front", facing="north") is None


def test_toilet_touching_road_is_rejected():
    inner, rp, rt = _make_rooms_with_road_contact("toilet")
    assert find_entrance_wall(inner, rp, rt, side="front", facing="north") is None


def test_kitchen_touching_road_is_rejected():
    inner, rp, rt = _make_rooms_with_road_contact("kitchen")
    assert find_entrance_wall(inner, rp, rt, side="front", facing="north") is None


def test_parking_touching_road_is_rejected():
    inner, rp, rt = _make_rooms_with_road_contact("parking")
    assert find_entrance_wall(inner, rp, rt, side="front", facing="north") is None


def test_master_bedroom_touching_road_is_rejected():
    inner, rp, rt = _make_rooms_with_road_contact("master_bedroom")
    assert find_entrance_wall(inner, rp, rt, side="front", facing="north") is None


# ─────────────────────────────────────────────
# Priority ordering
# ─────────────────────────────────────────────

def test_foyer_beats_living():
    inner = _buildable()
    room_polygons = {
        "FOYER": Polygon([(0, 5), (5, 5), (5, 10), (0, 10)]),
        "LIVING": Polygon([(5, 5), (10, 5), (10, 10), (5, 10)]),
    }
    room_types = {"FOYER": "foyer", "LIVING": "living"}
    result = find_entrance_wall(inner, room_polygons, room_types, side="front", facing="north")
    assert result is not None
    assert result["room_id"] == "FOYER"


def test_living_beats_corridor():
    inner = _buildable()
    room_polygons = {
        "LIV": Polygon([(0, 5), (5, 5), (5, 10), (0, 10)]),
        "COR": Polygon([(5, 5), (10, 5), (10, 10), (5, 10)]),
    }
    room_types = {"LIV": "living", "COR": "corridor"}
    result = find_entrance_wall(inner, room_polygons, room_types, side="front", facing="north")
    assert result is not None
    assert result["room_id"] == "LIV"


def test_living_beats_dining():
    inner = _buildable()
    room_polygons = {
        "LIV": Polygon([(0, 5), (5, 5), (5, 10), (0, 10)]),
        "DIN": Polygon([(5, 5), (10, 5), (10, 10), (5, 10)]),
    }
    room_types = {"LIV": "living", "DIN": "dining"}
    result = find_entrance_wall(inner, room_polygons, room_types, side="front", facing="north")
    assert result is not None
    assert result["room_id"] == "LIV"


def test_foyer_beats_bedroom_on_road():
    inner = _buildable()
    room_polygons = {
        "FOYER": Polygon([(0, 5), (5, 5), (5, 10), (0, 10)]),
        "BED":   Polygon([(5, 5), (10, 5), (10, 10), (5, 10)]),
    }
    room_types = {"FOYER": "foyer", "BED": "bedroom"}
    result = find_entrance_wall(inner, room_polygons, room_types, side="front", facing="north")
    assert result is not None
    assert result["room_id"] == "FOYER"


def test_same_priority_longer_boundary_wins():
    """
    WIDE occupies 8 m of the road edge, NARROW only 2 m.
    Leave a clear gap between rooms so the 0.05 m buffer does not
    erroneously inflate the shorter room's shared length.
    """
    inner = _buildable()
    room_polygons = {
        "WIDE":   Polygon([(0, 5), (8, 5), (8, 10), (0, 10)]),   # 8 m road contact
        "NARROW": Polygon([(8, 5), (10, 5), (10, 10), (8, 10)]),  # 2 m road contact
    }
    room_types = {"WIDE": "dining", "NARROW": "dining"}
    result = find_entrance_wall(inner, room_polygons, room_types, side="front", facing="north")
    assert result is not None
    assert result["room_id"] == "WIDE"


# ─────────────────────────────────────────────
# No eligible room → None
# ─────────────────────────────────────────────

def test_returns_none_when_no_room_touches_road():
    """
    The room is inset 1 m from every edge of the buildable polygon so that it
    does not share any boundary with the road-facing edges.
    """
    inner = _buildable()
    # Inset room — does not touch any boundary edge
    room_poly = Polygon([(1, 1), (9, 1), (9, 4), (1, 4)])
    result = find_entrance_wall(
        inner, {"R001": room_poly}, {"R001": "living"},
        side="front", facing="north",
    )
    assert result is None


def test_returns_none_all_ineligible():
    inner = _buildable()
    room_polygons = {
        "BED": Polygon([(0, 5), (5, 5), (5, 10), (0, 10)]),
        "TOI": Polygon([(5, 5), (10, 5), (10, 10), (5, 10)]),
    }
    room_types = {"BED": "bedroom", "TOI": "toilet"}
    result = find_entrance_wall(inner, room_polygons, room_types, side="front", facing="north")
    assert result is None


# ─────────────────────────────────────────────
# Position sanity
# ─────────────────────────────────────────────

def test_entrance_position_is_near_road_boundary():
    inner = _buildable()
    room_poly = Polygon([(0, 5), (10, 5), (10, 10), (0, 10)])
    result = find_entrance_wall(inner, {"R001": room_poly}, {"R001": "living"},
                                 side="front", facing="north")
    assert result is not None
    y = result["position"]["y"]
    assert abs(y - 10.0) < 0.15


def test_entrance_direction_is_returned():
    inner = _buildable()
    room_poly = Polygon([(0, 5), (10, 5), (10, 10), (0, 10)])
    result = find_entrance_wall(inner, {"R001": room_poly}, {"R001": "living"},
                                 side="front", facing="north")
    assert result is not None
    assert "direction" in result
    assert result["direction"].endswith("deg")
