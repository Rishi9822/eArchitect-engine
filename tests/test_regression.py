"""
Regression test based on the original sample payload.

Verifies that the engine continues to generate valid layouts
for the known-good sample input.
"""
import pytest


class TestRegressionSamplePayload:
    """
    Regression against the original sample_payload.json that produced
    7 rooms with score 0.9098 in the prototype.
    """

    def test_sample_generates_valid_layout(self, client, sample_payload):
        resp = client.post("/api/v1/layouts/generate", json=sample_payload)
        assert resp.status_code == 200
        data = resp.json()

        # ── Top-level structure ──────────────────────────────────
        assert "layout" in data
        assert "plot" in data
        assert "buildable_area" in data
        assert "candidates" in data
        assert "best_candidate_id" in data

        # ── Plot output ──────────────────────────────────────────
        plot = data["plot"]
        assert len(plot["boundary"]) >= 5  # Pentagon
        assert plot["area_sqft"] > 0
        assert plot["area_sqm"] > 0

        # ── Buildable area ───────────────────────────────────────
        ba = data["buildable_area"]
        assert len(ba["boundary"]) >= 3
        assert ba["area_sqft"] > 0
        assert ba["setback_m"] == 2

        # ── At least one candidate ───────────────────────────────
        assert len(data["candidates"]) >= 1
        best_id = data["best_candidate_id"]
        best = next(c for c in data["candidates"] if c["id"] == best_id)

        # ── Rooms ────────────────────────────────────────────────
        rooms = best["rooms"]
        # Original generated 7 rooms (6 + parking); allow >= 6
        assert len(rooms) >= 6, f"Expected >= 6 rooms, got {len(rooms)}"

        # All requested types must be present
        room_types = [r["type"] for r in rooms]
        assert "living" in room_types
        assert "dining" in room_types
        assert "kitchen" in room_types
        assert "bedroom" in room_types
        assert "toilet" in room_types

        # Polygons valid
        for r in rooms:
            assert len(r["polygon"]) >= 3
            assert r["area_sqft"] > 0
            assert r["area_sqm"] > 0

        # ── Walls ────────────────────────────────────────────────
        walls = best["walls"]
        assert len(walls) >= 4  # At minimum several walls

        # No tiny wall artifacts
        for w in walls:
            assert w["length"] >= 0.10, (
                f"Wall {w.get('id')} has length {w['length']} < 0.10m"
            )
            assert w.get("id") is not None

        # ── Doors ────────────────────────────────────────────────
        doors = best["doors"]
        assert len(doors) >= 1

        # ── Windows ──────────────────────────────────────────────
        windows = best["windows"]
        # Ventilation-priority rooms should have windows
        assert len(windows) >= 1

        # ── Entrance ─────────────────────────────────────────────
        entrances = best["entrances"]
        assert len(entrances) >= 1

        # ── Parking ──────────────────────────────────────────────
        parking = best["parking"]
        assert len(parking) >= 1  # parking=True in payload

        # ── Circulation ──────────────────────────────────────────
        circ = best["circulation"]
        assert circ["total_rooms"] >= 6
        assert circ["reachable_rooms"] >= 1
        assert 0 <= circ["score"] <= 1

        # ── Score ────────────────────────────────────────────────
        score = best["score"]
        assert "overall" in score
        assert 0 < score["overall"] <= 1
        assert "buildable_utilization" in score
        assert "building_coverage" in score
        assert "adjacency" in score
        assert "circulation" in score
        assert "natural_light" in score
        assert "ventilation" in score

        # ── Measurements ─────────────────────────────────────────
        m = best["measurements"]
        assert m["plot_area_sqm"] > 0
        assert m["plot_area_sqft"] > 0
        assert m["buildable_area_sqm"] > 0
        assert m["exterior_wall_length_m"] > 0
        assert m["total_wall_length_m"] > 0
        assert m["total_door_count"] >= 1
        assert m["total_window_count"] >= 1

        # ── Metrics ──────────────────────────────────────────────
        met = best["metrics"]
        assert 0 < met["building_coverage"] < 1
        assert met["building_coverage_percentage"] > 0

        # ── Validation ───────────────────────────────────────────
        val = best["validation"]
        assert len(val["constraints_checked"]) >= 5


class TestRegressionBackwardCompat:
    """The old /generate-layout endpoint should still work."""

    def test_old_endpoint_works(self, client, sample_payload):
        resp = client.post("/generate-layout", json=sample_payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "candidates" in data


class TestRegressionSampleFiles:
    """Run all JSON files in samples/ through the API."""

    @pytest.mark.parametrize(
        "filename",
        [
            "rectangle.json",
            "pentagon.json",
            "hexagon.json",
            "trapezoid.json",
            "irregular.json",
            "parking.json",
            "multi_candidate.json",
        ],
    )
    def test_sample_files_generate_valid_response(self, client, filename):
        import json
        from pathlib import Path
        path = Path("samples") / filename
        with open(path, "r") as f:
            payload = json.load(f)

        resp = client.post("/api/v1/layouts/generate", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["candidates"]) >= 1
        assert data["best_candidate_id"] == data["candidates"][0]["id"]
        for c in data["candidates"]:
            assert "strategy" in c
            assert "variation" in c
            assert len(c["rooms"]) >= 1
            assert len(c["walls"]) >= 1
            assert "measurements" in c
            assert "metrics" in c
            assert "score" in c

    def test_impossible_sample_fails_with_422(self, client):
        import json
        from pathlib import Path
        path = Path("samples") / "impossible.json"
        with open(path, "r") as f:
            payload = json.load(f)

        resp = client.post("/api/v1/layouts/generate", json=payload)
        assert resp.status_code == 422
        data = resp.json()
        assert data["error_code"] == "LAYOUT_INFEASIBLE"
