"""
Pytest configuration and shared fixtures.
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def rectangle_payload():
    """Simple rectangular plot payload."""
    return {
        "plot": {
            "points": [
                {"x": 0, "y": 0}, {"x": 15, "y": 0},
                {"x": 15, "y": 12}, {"x": 0, "y": 12}
            ],
            "facing": "north",
            "road_side": "front",
            "setback": 1.5,
        },
        "rooms": [
            {"type": "living", "count": 1, "min_area": 150},
            {"type": "kitchen", "count": 1, "min_area": 80},
            {"type": "bedroom", "count": 2, "min_area": 120},
            {"type": "toilet", "count": 1, "min_area": 40},
        ],
        "entrance": {"side": "front", "width": 1.2},
        "preferences": {
            "parking": False,
            "ventilation_priority": True,
            "natural_light_priority": False,
        },
    }


@pytest.fixture
def pentagon_payload():
    """Irregular pentagonal plot payload."""
    return {
        "plot": {
            "points": [
                {"x": 0, "y": 0}, {"x": 18, "y": 0},
                {"x": 20, "y": 8}, {"x": 10, "y": 16}, {"x": 0, "y": 12}
            ],
            "facing": "north",
            "road_side": "front",
            "setback": 2.0,
        },
        "rooms": [
            {"type": "living", "count": 1, "min_area": 150},
            {"type": "dining", "count": 1, "min_area": 100},
            {"type": "kitchen", "count": 1, "min_area": 80},
            {"type": "bedroom", "count": 2, "min_area": 120},
            {"type": "toilet", "count": 1, "min_area": 40},
        ],
        "entrance": {"side": "front", "width": 1.2},
        "preferences": {
            "parking": True,
            "ventilation_priority": True,
            "natural_light_priority": True,
        },
    }


@pytest.fixture
def sample_payload():
    """Original sample payload from the repository."""
    return {
        "plot": {
            "points": [
                {"x": 0, "y": 0}, {"x": 15, "y": 0},
                {"x": 18, "y": 6}, {"x": 12, "y": 14}, {"x": 0, "y": 12}
            ],
            "facing": "north",
            "road_side": "front",
            "setback": 2,
        },
        "rooms": [
            {"type": "living", "count": 1, "min_area": 150},
            {"type": "dining", "count": 1, "min_area": 100},
            {"type": "kitchen", "count": 1, "min_area": 80},
            {"type": "bedroom", "count": 2, "min_area": 120},
            {"type": "toilet", "count": 1, "min_area": 40},
        ],
        "entrance": {"side": "front", "width": 5},
        "preferences": {
            "parking": True,
            "ventilation_priority": True,
            "natural_light_priority": False,
        },
    }


@pytest.fixture
def impossible_payload():
    """Payload that requires more area than available."""
    return {
        "plot": {
            "points": [
                {"x": 0, "y": 0}, {"x": 5, "y": 0},
                {"x": 5, "y": 5}, {"x": 0, "y": 5}
            ],
            "facing": "north",
            "road_side": "front",
            "setback": 1.0,
        },
        "rooms": [
            {"type": "living", "count": 1, "min_area": 500},
            {"type": "bedroom", "count": 3, "min_area": 300},
            {"type": "kitchen", "count": 1, "min_area": 200},
        ],
        "entrance": {"side": "front", "width": 1.2},
        "preferences": {"parking": False},
    }
