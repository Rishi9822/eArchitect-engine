"""
Comprehensive test suite for Multi-Strategy Layout Generation, Corridors,
Diversity, Fingerprinting, and Ranking.

Covers all 20 architectural requirements:
1. Multiple candidates are actually geometrically different.
2. Same seed gives identical candidate sets.
3. Different seed produces different candidate layouts.
4. Duplicate candidates are removed via fingerprinting.
5. Strategy changes actual geometry.
6. open_plan produces no dedicated corridor.
7. central_corridor produces a corridor.
8. side_corridor produces a corridor.
9. corridor remains inside buildable area.
10. corridor width is valid.
11. corridor is connected to intended rooms.
12. corridor is included correctly in circulation graph.
13. corridor area is not counted as room area.
14. wall lengths match coordinates across candidate strategies.
15. no overlapping duplicate interior walls in strategy layouts.
16. irregular plots work with corridor strategies.
17. parking layouts remain valid across strategies.
18. top 3 candidates are genuinely diverse.
19. ranking still prefers valid layouts over invalid ones.
20. backward-compatible endpoint still works and returns diverse candidates.
"""
import math
import pytest
from shapely.geometry import Polygon

from app.config import SQ_FT_TO_SQ_M, MIN_CORRIDOR_WIDTH_M
from app.geometry.normalization import normalize_polygon
from app.geometry.setback import apply_setback
from app.layout.bsp import build_room_specs, generate_bsp_layout
from app.layout.circulation import build_adjacency_graph, analyze_circulation
from app.layout.strategies import dispatch_strategy
from app.layout.strategies import open_plan, central_corridor, side_corridor, public_private, service_core, compact
from app.optimization.candidates import generate_candidates
from app.optimization.fingerprint import layout_fingerprint, deduplicate_candidates
from app.optimization.diversity import pairwise_diversity, select_diverse_candidates
from app.optimization.ranking import rank_candidates
from app.services.layout_service import generate_layout_response
from app.models.input_models import GenerateLayoutRequest


class TestMultiStrategyGeometry:
    """Test architectural generation strategies and candidate diversity."""

    def _sample_specs(self):
        return build_room_specs([
            {"id": "living_0", "type": "living", "min_area_sqm": 150 * SQ_FT_TO_SQ_M, "priority": 10},
            {"id": "dining_0", "type": "dining", "min_area_sqm": 100 * SQ_FT_TO_SQ_M, "priority": 15},
            {"id": "kitchen_0", "type": "kitchen", "min_area_sqm": 80 * SQ_FT_TO_SQ_M, "priority": 25},
            {"id": "bedroom_0", "type": "bedroom", "min_area_sqm": 120 * SQ_FT_TO_SQ_M, "priority": 20},
            {"id": "bedroom_1", "type": "bedroom", "min_area_sqm": 120 * SQ_FT_TO_SQ_M, "priority": 20},
            {"id": "toilet_0", "type": "toilet", "min_area_sqm": 40 * SQ_FT_TO_SQ_M, "priority": 30},
        ], {"parking": False})

    def _buildable_rect(self):
        return Polygon([(0, 0), (20, 0), (20, 15), (0, 15)])

    # Requirement 1: Multiple candidates are actually geometrically different
    def test_1_multiple_candidates_geometrically_different(self, client, rectangle_payload):
        rectangle_payload["candidate_count"] = 5
        rectangle_payload["seed"] = 42
        resp = client.post("/api/v1/layouts/generate", json=rectangle_payload)
        assert resp.status_code == 200
        candidates = resp.json()["candidates"]
        assert len(candidates) >= 2

        # Check centroids across candidates differ
        centroids_set = set()
        for cand in candidates:
            c_tuple = tuple((r["id"], round(r["centroid"]["x"], 2), round(r["centroid"]["y"], 2))
                            for r in cand["rooms"])
            centroids_set.add(c_tuple)

        assert len(centroids_set) > 1, "Candidates must have different room centroids!"

    # Requirement 2: Same seed gives identical candidate sets
    def test_2_deterministic_with_same_seed(self, client, rectangle_payload):
        rectangle_payload["candidate_count"] = 3
        rectangle_payload["seed"] = 12345

        resp1 = client.post("/api/v1/layouts/generate", json=rectangle_payload).json()
        resp2 = client.post("/api/v1/layouts/generate", json=rectangle_payload).json()

        assert len(resp1["candidates"]) == len(resp2["candidates"])
        for c1, c2 in zip(resp1["candidates"], resp2["candidates"]):
            assert c1["strategy"] == c2["strategy"]
            assert len(c1["rooms"]) == len(c2["rooms"])
            for r1, r2 in zip(c1["rooms"], c2["rooms"]):
                assert r1["id"] == r2["id"]
                assert abs(r1["centroid"]["x"] - r2["centroid"]["x"]) < 1e-3
                assert abs(r1["centroid"]["y"] - r2["centroid"]["y"]) < 1e-3
                assert abs(r1["area_sqm"] - r2["area_sqm"]) < 1e-3

    # Requirement 3: Different seed can produce different arrangements
    def test_3_different_seed_different_arrangement(self, client, rectangle_payload):
        rectangle_payload["candidate_count"] = 3
        rectangle_payload["seed"] = 11111
        resp1 = client.post("/api/v1/layouts/generate", json=rectangle_payload).json()

        rectangle_payload["seed"] = 99999
        resp2 = client.post("/api/v1/layouts/generate", json=rectangle_payload).json()

        fp1 = [layout_fingerprint(c["rooms"]) for c in resp1["candidates"]]
        fp2 = [layout_fingerprint(c["rooms"]) for c in resp2["candidates"]]
        # At least one candidate differs
        assert fp1 != fp2

    # Requirement 4: Duplicate candidates are removed
    def test_4_duplicate_candidates_removed(self):
        c1 = {
            "id": "c1", "strategy": "open_plan",
            "rooms": [{"id": "r1", "type": "living", "centroid": {"x": 2.0, "y": 2.0}, "area_sqm": 20.0}],
        }
        c2 = {
            "id": "c2", "strategy": "compact",
            "rooms": [{"id": "r1", "type": "living", "centroid": {"x": 2.0, "y": 2.0}, "area_sqm": 20.0}],
        }
        c3 = {
            "id": "c3", "strategy": "side_corridor",
            "rooms": [{"id": "r1", "type": "living", "centroid": {"x": 8.0, "y": 5.0}, "area_sqm": 18.0}],
        }

        unique = deduplicate_candidates([c1, c2, c3])
        assert len(unique) == 2
        assert unique[0]["id"] == "c1"
        assert unique[1]["id"] == "c3"

    # Requirement 5: Strategy changes actual geometry
    def test_5_strategy_changes_geometry(self):
        poly = self._buildable_rect()
        specs = self._sample_specs()
        import random

        r_open = open_plan.generate(poly, specs, random.Random(42))
        r_service = service_core.generate(poly, specs, random.Random(42))

        # Check centroids of rooms differ between open_plan and service_core
        centroids_open = {rid: node.polygon.centroid for rid, node in r_open["room_leaves"].items()}
        centroids_svc = {rid: node.polygon.centroid for rid, node in r_service["room_leaves"].items()}

        diff_count = sum(
            1 for rid in centroids_open
            if rid in centroids_svc and abs(centroids_open[rid].x - centroids_svc[rid].x) > 0.5
            or abs(centroids_open[rid].y - centroids_svc[rid].y) > 0.5
        )
        assert diff_count > 0, "open_plan and service_core must produce different room placements"

    # Requirement 6: open_plan produces no dedicated corridor
    def test_6_open_plan_no_dedicated_corridor(self):
        poly = self._buildable_rect()
        specs = self._sample_specs()
        import random
        res = open_plan.generate(poly, specs, random.Random(42))
        assert len(res.get("corridors", [])) == 0

    # Requirement 7: central_corridor produces a corridor
    def test_7_central_corridor_produces_corridor(self):
        poly = self._buildable_rect()
        specs = self._sample_specs()
        import random
        res = central_corridor.generate(poly, specs, random.Random(42))
        corridors = res.get("corridors", [])
        assert len(corridors) >= 1
        assert corridors[0]["type"] == "corridor"
        assert corridors[0]["area_sqm"] > 0

    # Requirement 8: side_corridor produces a corridor
    def test_8_side_corridor_produces_corridor(self):
        poly = self._buildable_rect()
        specs = self._sample_specs()
        import random
        res = side_corridor.generate(poly, specs, random.Random(42))
        corridors = res.get("corridors", [])
        assert len(corridors) >= 1
        assert corridors[0]["type"] == "corridor"
        assert corridors[0]["area_sqm"] > 0

    # Requirement 9: corridor remains inside buildable area
    def test_9_corridor_inside_buildable_area(self):
        poly = self._buildable_rect()
        specs = self._sample_specs()
        import random
        res = central_corridor.generate(poly, specs, random.Random(42))
        corridor_polys = res.get("corridor_polygons", [])
        assert len(corridor_polys) >= 1
        for cp in corridor_polys:
            assert poly.contains(cp) or poly.buffer(0.01).contains(cp)

    # Requirement 10: corridor width is valid
    def test_10_corridor_width_valid(self):
        poly = self._buildable_rect()
        specs = self._sample_specs()
        import random
        res = central_corridor.generate(poly, specs, random.Random(42))
        corridors = res.get("corridors", [])
        assert len(corridors) >= 1
        assert corridors[0]["width"] >= MIN_CORRIDOR_WIDTH_M * 0.9

    # Requirement 11: corridor is connected to intended rooms
    def test_11_corridor_connected_to_rooms(self):
        poly = self._buildable_rect()
        specs = self._sample_specs()
        import random
        res = central_corridor.generate(poly, specs, random.Random(42))
        corridors = res.get("corridors", [])
        assert len(corridors) >= 1
        assert len(corridors[0]["connected_rooms"]) > 0

    # Requirement 12: corridor is included correctly in circulation graph
    def test_12_corridor_in_circulation_graph(self):
        poly = self._buildable_rect()
        specs = self._sample_specs()
        import random
        res = central_corridor.generate(poly, specs, random.Random(42))
        room_polys = {rid: leaf.polygon for rid, leaf in res["room_leaves"].items()}
        corridors = res.get("corridors", [])
        corr_polys = res.get("corridor_polygons", [])

        graph = build_adjacency_graph(
            room_polys, doors=[], entrance={"room_id": "living_0"},
            corridors=corridors, corridor_polygons=corr_polys,
        )
        assert "corridor_0" in graph
        assert len(graph["corridor_0"]) > 0

        circ = analyze_circulation(graph, list(room_polys.keys()), "living_0")
        assert circ["connected"] is True
        assert circ["reachable_rooms"] == len(room_polys)

    # Requirement 13: corridor area is not counted as room area
    def test_13_corridor_area_separate_from_room_area(self, client, rectangle_payload):
        rectangle_payload["candidate_count"] = 5
        rectangle_payload["seed"] = 42
        resp = client.post("/api/v1/layouts/generate", json=rectangle_payload)
        candidates = resp.json()["candidates"]

        corridor_cands = [c for c in candidates if c.get("corridors")]
        if corridor_cands:
            cand = corridor_cands[0]
            corr_area = sum(c["area_sqm"] for c in cand["corridors"])
            room_area = cand["measurements"]["room_area_sqm"]
            built_up = cand["measurements"]["built_up_area_sqm"]

            # Room area should be sum of rooms ONLY
            calc_room_area = sum(r["area_sqm"] for r in cand["rooms"])
            assert abs(room_area - calc_room_area) < 0.1

            # Built-up area includes corridor area
            assert abs(built_up - (room_area + corr_area)) < 0.1

    # Requirement 14: wall lengths match coordinates
    def test_14_wall_length_matches_coordinates(self, client, rectangle_payload):
        rectangle_payload["candidate_count"] = 5
        rectangle_payload["seed"] = 42
        resp = client.post("/api/v1/layouts/generate", json=rectangle_payload)
        candidates = resp.json()["candidates"]

        for cand in candidates:
            for wall in cand["walls"]:
                sx, sy = wall["start"]["x"], wall["start"]["y"]
                ex, ey = wall["end"]["x"], wall["end"]["y"]
                coord_len = math.sqrt((ex - sx)**2 + (ey - sy)**2)
                assert abs(coord_len - wall["length"]) < 0.05, (
                    f"Candidate {cand['id']} wall {wall['id']} length mismatch: "
                    f"coord={coord_len:.3f}, reported={wall['length']:.3f}"
                )

    # Requirement 15: no overlapping duplicate interior walls
    def test_15_no_duplicate_interior_walls(self, client, rectangle_payload):
        rectangle_payload["candidate_count"] = 5
        rectangle_payload["seed"] = 42
        resp = client.post("/api/v1/layouts/generate", json=rectangle_payload)
        candidates = resp.json()["candidates"]

        for cand in candidates:
            int_walls = [w for w in cand["walls"] if w["type"] == "interior"]
            seen_pairs = set()
            for w in int_walls:
                pair = tuple(sorted([w.get("room_a") or "", w.get("room_b") or ""]))
                # Check for exact duplicate wall coordinates
                start = (round(w["start"]["x"], 2), round(w["start"]["y"], 2))
                end = (round(w["end"]["x"], 2), round(w["end"]["y"], 2))
                wall_geom = tuple(sorted([start, end]))
                assert wall_geom not in seen_pairs, (
                    f"Duplicate interior wall geometry detected in {cand['id']}: {w['id']}"
                )
                seen_pairs.add(wall_geom)

    # Requirement 16: irregular plots work with corridor strategies
    def test_16_irregular_plots_work_with_corridors(self, client, pentagon_payload):
        pentagon_payload["candidate_count"] = 5
        pentagon_payload["seed"] = 42
        resp = client.post("/api/v1/layouts/generate", json=pentagon_payload)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["candidates"]) >= 2
        # Best candidate must be valid
        assert data["candidates"][0]["validation"]["valid"] is True
        # Check that corridor strategies were generated and valid
        strategies = {c["strategy"]: c for c in data["candidates"]}
        assert "central_corridor" in strategies or "side_corridor" in strategies
        for s_name in ["central_corridor", "side_corridor"]:
            if s_name in strategies:
                assert strategies[s_name]["validation"]["valid"] is True
                assert len(strategies[s_name]["rooms"]) > 0

    # Requirement 17: parking layouts remain valid across strategies
    def test_17_parking_valid_across_strategies(self, client, pentagon_payload):
        pentagon_payload["candidate_count"] = 5
        pentagon_payload["seed"] = 42
        pentagon_payload["preferences"]["parking"] = True
        resp = client.post("/api/v1/layouts/generate", json=pentagon_payload)
        assert resp.status_code == 200
        candidates = resp.json()["candidates"]

        for cand in candidates:
            if cand.get("parking"):
                for p in cand["parking"]:
                    assert p["area_sqm"] > 0
                    assert p["width_m"] > 0
                    assert p["length_m"] > 0

    # Requirement 18: top 3 candidates are genuinely diverse
    def test_18_top_candidates_diverse(self, client, rectangle_payload):
        rectangle_payload["candidate_count"] = 3
        rectangle_payload["seed"] = 42
        resp = client.post("/api/v1/layouts/generate", json=rectangle_payload)
        candidates = resp.json()["candidates"]
        assert len(candidates) == 3

        # Pairwise diversity check
        div_01 = pairwise_diversity(candidates[0], candidates[1])
        div_02 = pairwise_diversity(candidates[0], candidates[2])
        div_12 = pairwise_diversity(candidates[1], candidates[2])

        assert div_01 > 0.05 or div_02 > 0.05 or div_12 > 0.05, (
            "Top 3 candidates must be diverse from each other"
        )

    # Requirement 19: ranking prefers valid layouts
    def test_19_ranking_prefers_valid_layouts(self):
        c_invalid_high_score = {
            "id": "c_inv", "strategy": "open_plan",
            "validation": {"valid": False},
            "score": {"overall": 0.99},
            "rooms": [{"id": "r1", "type": "living", "centroid": {"x": 1, "y": 1}, "area_sqm": 10}],
        }
        c_valid_normal_score = {
            "id": "c_val", "strategy": "compact",
            "validation": {"valid": True},
            "score": {"overall": 0.80},
            "rooms": [{"id": "r1", "type": "living", "centroid": {"x": 5, "y": 5}, "area_sqm": 12}],
        }

        ranked = rank_candidates([c_invalid_high_score, c_valid_normal_score])
        assert ranked[0]["id"] == "c_val"
        assert ranked[1]["id"] == "c_inv"

    # Requirement 20: backward-compatible endpoint works
    def test_20_backward_compatible_endpoint(self, client, rectangle_payload):
        rectangle_payload["candidate_count"] = 3
        resp = client.post("/generate-layout", json=rectangle_payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "candidates" in data
        assert len(data["candidates"]) == 3
        assert "best_candidate_id" in data
