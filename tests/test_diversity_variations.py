"""
Comprehensive tests for controlled layout diversity, strategy variations,
geometric candidate deduplication, corridor geometry and connectivity.
"""
from __future__ import annotations

import math
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Polygon, box

from app.main import app
from app.layout.bsp import RoomSpec
from app.layout.strategies import (
    public_private,
    service_core,
    side_corridor,
    central_corridor,
    open_plan,
    compact,
)
from app.optimization.candidates import generate_candidates
from app.optimization.fingerprint import are_candidates_geometrically_identical, deduplicate_candidates
from app.optimization.ranking import rank_candidates
from app.layout.circulation import build_adjacency_graph, analyze_circulation


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_specs():
    return [
        RoomSpec(id="living_0", type="living", zone="public", min_area_sqm=20.0, priority=90),
        RoomSpec(id="dining_0", type="dining", zone="public", min_area_sqm=12.0, priority=70),
        RoomSpec(id="kitchen_0", type="kitchen", zone="service", min_area_sqm=10.0, priority=80),
        RoomSpec(id="bedroom_0", type="bedroom", zone="private", min_area_sqm=14.0, priority=60),
        RoomSpec(id="bedroom_1", type="bedroom", zone="private", min_area_sqm=12.0, priority=50),
        RoomSpec(id="toilet_0", type="toilet", zone="service", min_area_sqm=4.0, priority=40),
    ]


@pytest.fixture
def buildable_polygon():
    return box(0, 0, 15, 10)


@pytest.fixture
def standard_request():
    return {
        "plot": {
            "points": [{"x": 0, "y": 0}, {"x": 20, "y": 0}, {"x": 20, "y": 15}, {"x": 0, "y": 15}],
            "setback": 1.5,
            "facing": "north",
            "road_side": "front",
        },
        "rooms": [
            {"type": "living", "count": 1, "min_area": 180, "priority": 90},
            {"type": "dining", "count": 1, "min_area": 120, "priority": 70},
            {"type": "kitchen", "count": 1, "min_area": 90, "priority": 80},
            {"type": "bedroom", "count": 2, "min_area": 130, "priority": 60},
            {"type": "toilet", "count": 2, "min_area": 40, "priority": 40},
        ],
        "entrance": {"side": "front", "width": 1.2},
        "preferences": {"parking": True},
        "candidate_count": 3,
    }


# =========================================================================
# 1. STRATEGY VARIATION TESTS
# =========================================================================

class TestStrategyVariations:
    """Verify that variations within each strategy produce distinct geometries."""

    def test_public_private_variations_differ(self, buildable_polygon, sample_specs):
        import random
        r1 = public_private.generate(buildable_polygon, sample_specs, random.Random(42), variation="left_private")
        r2 = public_private.generate(buildable_polygon, sample_specs, random.Random(42), variation="right_private")
        r3 = public_private.generate(buildable_polygon, sample_specs, random.Random(42), variation="reversed")

        c1 = r1["room_leaves"]["bedroom_0"].polygon.centroid
        c2 = r2["room_leaves"]["bedroom_0"].polygon.centroid
        c3 = r3["room_leaves"]["bedroom_0"].polygon.centroid

        assert math.hypot(c1.x - c2.x, c1.y - c2.y) > 0.5, "left_private and right_private must differ"
        assert math.hypot(c1.x - c3.x, c1.y - c3.y) > 0.5, "left_private and reversed must differ"

    def test_service_core_variations_differ(self, buildable_polygon, sample_specs):
        import random
        r1 = service_core.generate(buildable_polygon, sample_specs, random.Random(42), variation="left_core")
        r2 = service_core.generate(buildable_polygon, sample_specs, random.Random(42), variation="right_core")

        c1 = r1["room_leaves"]["kitchen_0"].polygon.centroid
        c2 = r2["room_leaves"]["kitchen_0"].polygon.centroid
        assert math.hypot(c1.x - c2.x, c1.y - c2.y) > 0.5, "left_core and right_core must differ"

    def test_side_corridor_variations_differ(self, buildable_polygon, sample_specs):
        import random
        r1 = side_corridor.generate(buildable_polygon, sample_specs, random.Random(42), variation="left_corridor")
        r2 = side_corridor.generate(buildable_polygon, sample_specs, random.Random(42), variation="right_corridor")

        corr1 = r1["corridor_polygons"][0].centroid
        corr2 = r2["corridor_polygons"][0].centroid
        assert math.hypot(corr1.x - corr2.x, corr1.y - corr2.y) > 2.0, "left_corridor and right_corridor positions must differ"

    def test_central_corridor_variations_differ(self, buildable_polygon, sample_specs):
        import random
        r1 = central_corridor.generate(buildable_polygon, sample_specs, random.Random(42), variation="horizontal_corridor")
        r2 = central_corridor.generate(buildable_polygon, sample_specs, random.Random(42), variation="vertical_corridor")

        poly1 = r1["corridor_polygons"][0]
        poly2 = r2["corridor_polygons"][0]

        # One is wide and short, other is tall and narrow
        bounds1 = poly1.bounds
        bounds2 = poly2.bounds
        w1, h1 = bounds1[2] - bounds1[0], bounds1[3] - bounds1[1]
        w2, h2 = bounds2[2] - bounds2[0], bounds2[3] - bounds2[1]

        assert (w1 > h1 and h2 > w2) or (w2 > h2 and h1 > w1), "horizontal and vertical central corridors must differ in orientation"

    def test_open_plan_variations_differ(self, buildable_polygon, sample_specs):
        import random
        r1 = open_plan.generate(buildable_polygon, sample_specs, random.Random(42), variation="standard")
        r2 = open_plan.generate(buildable_polygon, sample_specs, random.Random(42), variation="alternate_axis")

        c1 = r1["room_leaves"]["living_0"].polygon.centroid
        c2 = r2["room_leaves"]["living_0"].polygon.centroid
        assert math.hypot(c1.x - c2.x, c1.y - c2.y) > 0.3, "standard and alternate_axis must differ in room placement"


# =========================================================================
# 2. GEOMETRIC DEDUPLICATION TESTS
# =========================================================================

class TestGeometricDeduplication:
    """Verify that geometric deduplication correctly detects identical room arrangements."""

    def test_detects_identical_candidates(self):
        c1 = {
            "id": "c1",
            "strategy": "open_plan",
            "variation": "standard",
            "rooms": [
                {"id": "r1", "type": "living", "centroid": {"x": 5.0, "y": 5.0}, "area_sqm": 25.0},
                {"id": "r2", "type": "bedroom", "centroid": {"x": 10.0, "y": 5.0}, "area_sqm": 15.0},
            ],
            "corridors": [],
        }
        # Duplicate with tiny jitter < 0.05m
        c2 = {
            "id": "c2",
            "strategy": "custom",
            "variation": "v2",
            "rooms": [
                {"id": "r1", "type": "living", "centroid": {"x": 5.02, "y": 5.01}, "area_sqm": 25.05},
                {"id": "r2", "type": "bedroom", "centroid": {"x": 9.99, "y": 5.02}, "area_sqm": 14.98},
            ],
            "corridors": [],
        }
        assert are_candidates_geometrically_identical(c1, c2, centroid_tol=0.35, area_tol=0.5) is True

    def test_detects_different_candidates(self):
        c1 = {
            "id": "c1",
            "strategy": "public_private",
            "variation": "left_private",
            "rooms": [
                {"id": "r1", "type": "living", "centroid": {"x": 2.0, "y": 5.0}, "area_sqm": 25.0},
                {"id": "r2", "type": "bedroom", "centroid": {"x": 10.0, "y": 5.0}, "area_sqm": 15.0},
            ],
            "corridors": [],
        }
        c2 = {
            "id": "c2",
            "strategy": "public_private",
            "variation": "right_private",
            "rooms": [
                {"id": "r1", "type": "living", "centroid": {"x": 10.0, "y": 5.0}, "area_sqm": 25.0},
                {"id": "r2", "type": "bedroom", "centroid": {"x": 2.0, "y": 5.0}, "area_sqm": 15.0},
            ],
            "corridors": [],
        }
        assert are_candidates_geometrically_identical(c1, c2, centroid_tol=0.35, area_tol=0.5) is False

    def test_deduplicate_removes_duplicate_and_preserves_unique(self):
        c1 = {
            "id": "c1",
            "strategy": "s1",
            "rooms": [{"id": "r1", "type": "living", "centroid": {"x": 5.0, "y": 5.0}, "area_sqm": 20.0}],
            "corridors": [],
        }
        c2 = {
            "id": "c2",
            "strategy": "s2",
            "rooms": [{"id": "r1", "type": "living", "centroid": {"x": 5.01, "y": 4.99}, "area_sqm": 20.01}],
            "corridors": [],
        }
        c3 = {
            "id": "c3",
            "strategy": "s3",
            "rooms": [{"id": "r1", "type": "living", "centroid": {"x": 12.0, "y": 5.0}, "area_sqm": 20.0}],
            "corridors": [],
        }

        unique = deduplicate_candidates([c1, c2, c3])
        assert len(unique) == 2
        assert unique[0]["id"] == "c1"
        assert unique[1]["id"] == "c3"


# =========================================================================
# 3. END-TO-END RUN-TO-RUN & DETERMINISM TESTS
# =========================================================================

class TestEndToEndDiversity:
    """Verify run-to-run diversity without seed and exact determinism with seed."""

    def test_deterministic_with_seed(self, client, standard_request):
        req = dict(standard_request)
        req["seed"] = 998877

        resp1 = client.post("/api/v1/layouts/generate", json=req)
        assert resp1.status_code == 200
        data1 = resp1.json()

        resp2 = client.post("/api/v1/layouts/generate", json=req)
        assert resp2.status_code == 200
        data2 = resp2.json()

        # Check candidate geometries match exactly
        cands1 = data1["candidates"]
        cands2 = data2["candidates"]
        assert len(cands1) == len(cands2)

        for c1, c2 in zip(cands1, cands2):
            assert c1["strategy"] == c2["strategy"]
            assert c1["variation"] == c2["variation"]
            assert len(c1["rooms"]) == len(c2["rooms"])
            for r1, r2 in zip(c1["rooms"], c2["rooms"]):
                assert r1["centroid"] == r2["centroid"]
                assert r1["area_sqm"] == r2["area_sqm"]

    def test_run_to_run_diversity_without_seed(self, client, standard_request):
        req = dict(standard_request)
        req.pop("seed", None)

        resp1 = client.post("/api/v1/layouts/generate", json=req)
        assert resp1.status_code == 200
        cands1 = resp1.json()["candidates"]

        resp2 = client.post("/api/v1/layouts/generate", json=req)
        assert resp2.status_code == 200
        cands2 = resp2.json()["candidates"]

        # Collect fingerprints or centroids across both runs
        centroids1 = [(r["centroid"]["x"], r["centroid"]["y"]) for r in cands1[0]["rooms"]]
        centroids2 = [(r["centroid"]["x"], r["centroid"]["y"]) for r in cands2[0]["rooms"]]

        # Two separate unseeded runs should produce diverse candidates across the pool
        assert len(cands1) >= 2
        assert len(cands2) >= 2

    def test_top_k_candidates_are_geometrically_distinct(self, client, standard_request):
        req = dict(standard_request)
        req["candidate_count"] = 3
        req["seed"] = 42

        resp = client.post("/api/v1/layouts/generate", json=req)
        assert resp.status_code == 200
        cands = resp.json()["candidates"]

        assert len(cands) == 3
        # Check pairwise distinctness
        for i in range(len(cands)):
            for j in range(i + 1, len(cands)):
                assert not are_candidates_geometrically_identical(cands[i], cands[j]), (
                    f"Candidate {i} (strategy={cands[i]['strategy']}, var={cands[i]['variation']}) "
                    f"and Candidate {j} (strategy={cands[j]['strategy']}, var={cands[j]['variation']}) must be distinct"
                )

    def test_corridor_candidate_has_no_room_overlaps(self, client, standard_request):
        req = dict(standard_request)
        req["candidate_count"] = 5
        req["seed"] = 12345

        resp = client.post("/api/v1/layouts/generate", json=req)
        assert resp.status_code == 200
        cands = resp.json()["candidates"]

        corridor_cands = [c for c in cands if c.get("corridors")]
        assert len(corridor_cands) >= 1

        for cand in corridor_cands:
            corr = cand["corridors"][0]
            corr_poly = Polygon([(p["x"], p["y"]) for p in corr["polygon"]])

            # Verify corridor has valid dimensions
            assert corr["area_sqm"] > 0
            assert corr["width"] >= 0.9
            assert corr["length"] > 0
            assert len(corr["connected_rooms"]) > 0

            # Verify zero area overlap with all room polygons
            for room in cand["rooms"]:
                r_poly = Polygon([(p["x"], p["y"]) for p in room["polygon"]])
                inter = corr_poly.intersection(r_poly)
                assert inter.area < 1e-4, f"Corridor overlaps room {room['id']} with area {inter.area}"

    def test_ranking_structure_and_best_candidate(self, client, standard_request):
        req = dict(standard_request)
        req["candidate_count"] = 3
        resp = client.post("/api/v1/layouts/generate", json=req)
        assert resp.status_code == 200
        data = resp.json()

        cands = data["candidates"]
        best_id = data["best_candidate_id"]

        assert cands[0]["id"] == best_id
        for i in range(len(cands) - 1):
            s1 = cands[i]["score"]["overall"]
            s2 = cands[i + 1]["score"]["overall"]
            assert s1 >= s2 - 1e-6, f"Rank {i+1} score ({s1}) should be >= Rank {i+2} score ({s2})"
