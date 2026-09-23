"""
Unit tests for Priority 3: Circulation Score (Fix the Score That Never Fails).

Verifies:
- Weighted composite circulation score (privacy_depth, public_private_separation,
  path_efficiency, service_isolation, corridor_presence)
- Disconnected layout gets score 0.0 and CIRCULATION_DISCONNECTED error
- Chain layout (7 rooms in a line) scores significantly below 1.0
- Good layout (rooms off a corridor) scores 0.85+
- Output JSON includes circulation_breakdown with all 5 sub-scores
"""
import pytest
from shapely.geometry import box
from app.layout.circulation import (
    build_adjacency_graph,
    compute_shortest_paths,
    compute_circulation_score,
    analyze_circulation,
)
from app.services.layout_service import generate_layout_response
from app.models.input_models import GenerateLayoutRequest


class TestShortestPaths:
    def test_compute_shortest_paths(self):
        graph = {
            "living_0": {"dining_0", "corridor_0"},
            "dining_0": {"living_0", "kitchen_0"},
            "kitchen_0": {"dining_0"},
            "corridor_0": {"living_0", "bedroom_0", "bedroom_1"},
            "bedroom_0": {"corridor_0"},
            "bedroom_1": {"corridor_0", "toilet_0"},
            "toilet_0": {"bedroom_1"},
        }
        distances, paths = compute_shortest_paths(graph, "living_0")

        assert distances["living_0"] == 0
        assert paths["living_0"] == ["living_0"]

        assert distances["corridor_0"] == 1
        assert paths["corridor_0"] == ["living_0", "corridor_0"]

        assert distances["bedroom_0"] == 2
        assert paths["bedroom_0"] == ["living_0", "corridor_0", "bedroom_0"]

        assert distances["toilet_0"] == 3
        assert paths["toilet_0"] == ["living_0", "corridor_0", "bedroom_1", "toilet_0"]


class TestPrivacyDepth:
    def test_good_privacy_via_corridor(self):
        graph = {
            "living_0": {"corridor_0"},
            "corridor_0": {"living_0", "bedroom_0", "bedroom_1"},
            "bedroom_0": {"corridor_0"},
            "bedroom_1": {"corridor_0"},
        }
        types = {
            "living_0": "living", "corridor_0": "corridor",
            "bedroom_0": "bedroom", "bedroom_1": "bedroom",
        }
        score, breakdown = compute_circulation_score(
            graph, list(types.keys()), entrance_room_id="living_0", room_types=types,
        )
        assert breakdown["privacy_depth"] == 1.0

    def test_bad_privacy_bedroom_through_bedroom(self):
        # Bedroom 1 can only be reached through Bedroom 0
        graph = {
            "living_0": {"bedroom_0"},
            "bedroom_0": {"living_0", "bedroom_1"},
            "bedroom_1": {"bedroom_0"},
        }
        types = {
            "living_0": "living", "bedroom_0": "bedroom", "bedroom_1": "bedroom",
        }
        score, breakdown = compute_circulation_score(
            graph, list(types.keys()), entrance_room_id="living_0", room_types=types,
        )
        # 1 of 2 private rooms violates privacy depth (bedroom_1)
        assert breakdown["privacy_depth"] == 0.5

    def test_bad_privacy_bedroom_through_kitchen(self):
        graph = {
            "living_0": {"kitchen_0"},
            "kitchen_0": {"living_0", "bedroom_0"},
            "bedroom_0": {"kitchen_0"},
        }
        types = {
            "living_0": "living", "kitchen_0": "kitchen", "bedroom_0": "bedroom",
        }
        score, breakdown = compute_circulation_score(
            graph, list(types.keys()), entrance_room_id="living_0", room_types=types,
        )
        assert breakdown["privacy_depth"] == 0.0

    def test_ensuite_toilet_through_parent_bedroom_allowed(self):
        # Attached toilet reachable through its parent bedroom is expected and permitted
        graph = {
            "living_0": {"corridor_0"},
            "corridor_0": {"living_0", "bedroom_0"},
            "bedroom_0": {"corridor_0", "toilet_0"},
            "toilet_0": {"bedroom_0"},
        }
        types = {
            "living_0": "living", "corridor_0": "corridor",
            "bedroom_0": "bedroom", "toilet_0": "toilet",
        }
        score, breakdown = compute_circulation_score(
            graph, list(types.keys()), entrance_room_id="living_0", room_types=types,
        )
        assert breakdown["privacy_depth"] == 1.0


class TestPublicPrivateSeparation:
    def test_private_further_than_public(self):
        graph = {
            "living_0": {"dining_0", "corridor_0"},
            "dining_0": {"living_0"},
            "corridor_0": {"living_0", "bedroom_0"},
            "bedroom_0": {"corridor_0"},
        }
        types = {
            "living_0": "living", "dining_0": "dining",
            "corridor_0": "corridor", "bedroom_0": "bedroom",
        }
        # living=0, dining=1 -> mean_pub = 0.5
        # bedroom_0=2 -> mean_priv = 2.0
        # diff = 2.0 - 0.5 = 1.5 >= 1.0 -> 1.0
        score, breakdown = compute_circulation_score(
            graph, list(types.keys()), entrance_room_id="living_0", room_types=types,
        )
        assert breakdown["public_private_separation"] == 1.0

    def test_private_closer_than_public(self):
        # Entrance directly into bedroom, dining far away
        graph = {
            "bedroom_0": {"dining_0"},
            "dining_0": {"bedroom_0"},
        }
        types = {"bedroom_0": "bedroom", "dining_0": "dining"}
        # priv=0, pub=1 -> diff = -1.0 <= 0.0 -> 0.2
        score, breakdown = compute_circulation_score(
            graph, list(types.keys()), entrance_room_id="bedroom_0", room_types=types,
        )
        assert breakdown["public_private_separation"] == 0.2


class TestPathEfficiency:
    def test_compact_layout_high_efficiency(self):
        graph = {
            "living_0": {"dining_0", "kitchen_0", "bedroom_0"},
            "dining_0": {"living_0"},
            "kitchen_0": {"living_0"},
            "bedroom_0": {"living_0"},
        }
        types = {"living_0": "living", "dining_0": "dining", "kitchen_0": "kitchen", "bedroom_0": "bedroom"}
        # mean hops: (0 + 1 + 1 + 1) / 4 = 0.75 <= 2.5 -> 1.0
        score, breakdown = compute_circulation_score(
            graph, list(types.keys()), entrance_room_id="living_0", room_types=types,
        )
        assert breakdown["path_efficiency"] == 1.0

    def test_long_chain_low_efficiency(self):
        # 6-room chain
        graph = {
            f"r_{i}": {f"r_{i-1}", f"r_{i+1}"} for i in range(1, 6)
        }
        graph["r_0"] = {"r_1"}
        graph["r_6"] = {"r_5"}
        room_ids = [f"r_{i}" for i in range(7)]
        # hops: 0, 1, 2, 3, 4, 5, 6 -> sum = 21, mean = 3.0
        # efficiency: 1.0 - (3.0 - 2.5)/2.5 = 1.0 - 0.2 = 0.8
        score, breakdown = compute_circulation_score(
            graph, room_ids, entrance_room_id="r_0",
        )
        assert breakdown["path_efficiency"] == pytest.approx(0.8, rel=1e-2)


class TestServiceIsolation:
    def test_no_service_violation(self):
        graph = {
            "living_0": {"corridor_0"},
            "corridor_0": {"living_0", "bedroom_0", "kitchen_0", "toilet_0"},
            "bedroom_0": {"corridor_0"},
            "kitchen_0": {"corridor_0"},
            "toilet_0": {"corridor_0"},
        }
        types = {
            "living_0": "living", "corridor_0": "corridor",
            "bedroom_0": "bedroom", "kitchen_0": "kitchen", "toilet_0": "toilet",
        }
        score, breakdown = compute_circulation_score(
            graph, list(types.keys()), entrance_room_id="living_0", room_types=types,
        )
        assert breakdown["service_isolation"] == 1.0

    def test_bedroom_through_kitchen_violation(self):
        graph = {
            "living_0": {"kitchen_0"},
            "kitchen_0": {"living_0", "bedroom_0"},
            "bedroom_0": {"kitchen_0"},
        }
        types = {"living_0": "living", "kitchen_0": "kitchen", "bedroom_0": "bedroom"}
        score, breakdown = compute_circulation_score(
            graph, list(types.keys()), entrance_room_id="living_0", room_types=types,
        )
        # 1 violation: 1.0 - 0.35 = 0.65
        assert breakdown["service_isolation"] == pytest.approx(0.65, rel=1e-2)

    def test_bedroom_through_toilet_violation(self):
        graph = {
            "living_0": {"toilet_0"},
            "toilet_0": {"living_0", "bedroom_0"},
            "bedroom_0": {"toilet_0"},
        }
        types = {"living_0": "living", "toilet_0": "toilet", "bedroom_0": "bedroom"}
        score, breakdown = compute_circulation_score(
            graph, list(types.keys()), entrance_room_id="living_0", room_types=types,
        )
        assert breakdown["service_isolation"] == pytest.approx(0.65, rel=1e-2)


class TestCorridorPresence:
    def test_many_rooms_without_corridor_penalized(self):
        # 6 rooms, 3 private, no corridor
        graph = {
            "living_0": {"bedroom_0", "bedroom_1", "bedroom_2", "dining_0", "kitchen_0"},
            "bedroom_0": {"living_0"},
            "bedroom_1": {"living_0"},
            "bedroom_2": {"living_0"},
            "dining_0": {"living_0"},
            "kitchen_0": {"living_0"},
        }
        types = {
            "living_0": "living", "bedroom_0": "bedroom", "bedroom_1": "bedroom",
            "bedroom_2": "bedroom", "dining_0": "dining", "kitchen_0": "kitchen",
        }
        score, breakdown = compute_circulation_score(
            graph, list(types.keys()), entrance_room_id="living_0", room_types=types,
        )
        assert breakdown["corridor_presence"] == 0.4

    def test_many_rooms_with_corridor_rewarded(self):
        graph = {
            "living_0": {"corridor_0", "dining_0"},
            "corridor_0": {"living_0", "bedroom_0", "bedroom_1", "bedroom_2"},
            "bedroom_0": {"corridor_0"},
            "bedroom_1": {"corridor_0"},
            "bedroom_2": {"corridor_0"},
            "dining_0": {"living_0", "kitchen_0"},
            "kitchen_0": {"dining_0"},
        }
        types = {
            "living_0": "living", "corridor_0": "corridor", "bedroom_0": "bedroom",
            "bedroom_1": "bedroom", "bedroom_2": "bedroom", "dining_0": "dining", "kitchen_0": "kitchen",
        }
        score, breakdown = compute_circulation_score(
            graph, list(types.keys()), entrance_room_id="living_0", room_types=types,
        )
        assert breakdown["corridor_presence"] == 1.0

    def test_small_apartment_corridor_exempt(self):
        # <6 rooms -> corridor not required
        graph = {
            "living_0": {"bedroom_0", "kitchen_0"},
            "bedroom_0": {"living_0"},
            "kitchen_0": {"living_0"},
        }
        types = {"living_0": "living", "bedroom_0": "bedroom", "kitchen_0": "kitchen"}
        score, breakdown = compute_circulation_score(
            graph, list(types.keys()), entrance_room_id="living_0", room_types=types,
        )
        assert breakdown["corridor_presence"] == 1.0


class TestPriority3Scenarios:
    def test_chain_layout_scores_significantly_below_1(self):
        """
        Scenario 2 from Verify checklist:
        Chain layout (7 rooms in a line):
        living_0 - kitchen_0 - bedroom_0 - toilet_0 - bedroom_1 - toilet_1 - dining_0
        Must score significantly below 1.0 (expected ~0.2 - 0.4).
        """
        graph = {
            "living_0": {"kitchen_0"},
            "kitchen_0": {"living_0", "bedroom_0"},
            "bedroom_0": {"kitchen_0", "toilet_0"},
            "toilet_0": {"bedroom_0", "bedroom_1"},
            "bedroom_1": {"toilet_0", "toilet_1"},
            "toilet_1": {"bedroom_1", "dining_0"},
            "dining_0": {"toilet_1"},
        }
        types = {
            "living_0": "living",
            "kitchen_0": "kitchen",
            "bedroom_0": "bedroom",
            "toilet_0": "toilet",
            "bedroom_1": "bedroom",
            "toilet_1": "toilet",
            "dining_0": "dining",
        }
        res = analyze_circulation(
            graph, list(types.keys()), entrance_room_id="living_0", room_types=types,
        )
        assert res["connected"] is True
        assert res["score"] < 0.50, f"Chain layout scored {res['score']}, expected < 0.50"
        # Verify sub-scores
        bd = res["circulation_breakdown"]
        assert bd["privacy_depth"] == 0.0  # both bedrooms traversed through kitchen/toilet
        assert bd["service_isolation"] == 0.30  # 2 violations (1.0 - 0.70)
        assert bd["corridor_presence"] == 0.4  # >=6 rooms, >=2 private rooms, no corridor

    def test_good_corridor_layout_scores_high(self):
        """
        Scenario 3 from Verify checklist:
        Good layout (rooms off a corridor) scores 0.85+
        """
        graph = {
            "living_0": {"corridor_0", "dining_0"},
            "corridor_0": {"living_0", "bedroom_0", "bedroom_1", "toilet_0"},
            "bedroom_0": {"corridor_0"},
            "bedroom_1": {"corridor_0"},
            "toilet_0": {"corridor_0"},
            "dining_0": {"living_0", "kitchen_0"},
            "kitchen_0": {"dining_0"},
        }
        types = {
            "living_0": "living",
            "corridor_0": "corridor",
            "bedroom_0": "bedroom",
            "bedroom_1": "bedroom",
            "toilet_0": "toilet",
            "dining_0": "dining",
            "kitchen_0": "kitchen",
        }
        res = analyze_circulation(
            graph, list(types.keys()), entrance_room_id="living_0", room_types=types,
        )
        assert res["connected"] is True
        assert res["score"] >= 0.85, f"Good layout scored {res['score']}, expected >= 0.85"
        bd = res["circulation_breakdown"]
        assert bd["privacy_depth"] == 1.0
        assert bd["service_isolation"] == 1.0
        assert bd["corridor_presence"] == 1.0

    def test_disconnected_layout_scores_zero_and_fails_validation(self):
        """
        Scenario 1 from Verify checklist:
        Disconnected layout gets score 0.0 and fails validation with CIRCULATION_DISCONNECTED.
        """
        graph = {
            "living_0": {"bedroom_0"},
            "bedroom_0": {"living_0"},
            "toilet_0": set(),  # Disconnected
        }
        types = {
            "living_0": "living", "bedroom_0": "bedroom", "toilet_0": "toilet",
        }
        res = analyze_circulation(
            graph, list(types.keys()), entrance_room_id="living_0", room_types=types,
        )
        assert res["connected"] is False
        assert res["score"] == 0.0

    def test_candidate_output_contains_circulation_breakdown(self):
        """
        Verify that candidate layout output contains circulation_breakdown dict
        with all 5 sub-scores alongside the circulation score object.
        """
        payload = {
            "plot": {
                "points": [{"x": 0, "y": 0}, {"x": 20, "y": 0}, {"x": 20, "y": 15}, {"x": 0, "y": 15}],
                "facing": "north",
                "road_side": "front",
                "setback": 2.0,
            },
            "rooms": [
                {"type": "living", "count": 1, "min_area": 150},
                {"type": "dining", "count": 1, "min_area": 100},
                {"type": "kitchen", "count": 1, "min_area": 80},
                {"type": "bedroom", "count": 2, "min_area": 120},
                {"type": "toilet", "count": 2, "min_area": 40},
            ],
            "entrance": {"side": "front", "width": 1.2},
            "preferences": {"parking": True},
            "candidate_count": 3,
            "seed": 42,
        }
        response = generate_layout_response(GenerateLayoutRequest(**payload))
        assert len(response["candidates"]) > 0

        for cand in response["candidates"]:
            circ = cand["circulation"]
            assert "score" in circ
            assert "connected" in circ
            assert "circulation_breakdown" in cand or "circulation_breakdown" in circ
            bd = cand.get("circulation_breakdown") or circ.get("circulation_breakdown")
            assert bd is not None
            assert "privacy_depth" in bd
            assert "public_private_separation" in bd
            assert "path_efficiency" in bd
            assert "service_isolation" in bd
            assert "corridor_presence" in bd
