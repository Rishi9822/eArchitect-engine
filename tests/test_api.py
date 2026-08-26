"""
Tests for API endpoints.
"""
import pytest


class TestHealthEndpoints:
    def test_root(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_v1_health(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_v1_version(self, client):
        resp = client.get("/api/v1/version")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data
        assert "api_version" in data


class TestGenerateEndpoint:
    def test_v1_generate_rectangle(self, client, rectangle_payload):
        resp = client.post("/api/v1/layouts/generate", json=rectangle_payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "candidates" in data
        assert len(data["candidates"]) >= 1

    def test_compat_generate(self, client, rectangle_payload):
        resp = client.post("/generate-layout", json=rectangle_payload)
        assert resp.status_code == 200

    def test_generate_with_multiple_candidates(self, client, rectangle_payload):
        rectangle_payload["candidate_count"] = 3
        rectangle_payload["seed"] = 42
        resp = client.post("/api/v1/layouts/generate", json=rectangle_payload)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["candidates"]) == 3


class TestErrorHandling:
    def test_invalid_plot_too_few_points(self, client):
        payload = {
            "plot": {
                "points": [{"x": 0, "y": 0}, {"x": 1, "y": 1}],
                "facing": "north", "road_side": "front", "setback": 1,
            },
            "rooms": [{"type": "living", "count": 1, "min_area": 100}],
            "entrance": {"side": "front", "width": 1.2},
        }
        resp = client.post("/api/v1/layouts/generate", json=payload)
        assert resp.status_code == 422

    def test_impossible_layout_returns_infeasible(self, client, impossible_payload):
        resp = client.post("/api/v1/layouts/generate", json=impossible_payload)
        assert resp.status_code == 422
        data = resp.json()
        assert data.get("error_code") == "LAYOUT_INFEASIBLE"

    def test_excessive_setback(self, client):
        payload = {
            "plot": {
                "points": [
                    {"x": 0, "y": 0}, {"x": 4, "y": 0},
                    {"x": 4, "y": 4}, {"x": 0, "y": 4}
                ],
                "facing": "north", "road_side": "front", "setback": 10,
            },
            "rooms": [{"type": "living", "count": 1, "min_area": 50}],
            "entrance": {"side": "front", "width": 1.2},
        }
        resp = client.post("/api/v1/layouts/generate", json=payload)
        assert resp.status_code == 422
        data = resp.json()
        assert data.get("error_code") == "NO_BUILDABLE_AREA"
