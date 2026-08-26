"""
Tests for parking constraints and entity generation.
"""
import pytest
from shapely.geometry import Polygon
from app.layout.parking import validate_parking, generate_parking_entities


class TestParkingValidation:
    def test_valid_parking(self):
        """Parking that meets minimum dimensions."""
        poly = Polygon([(0, 0), (3, 0), (3, 6), (0, 6)])  # 3m x 6m
        boundary = Polygon([(-1, -1), (4, -1), (4, 7), (-1, 7)])
        result = validate_parking(poly, boundary, "north", "front")
        assert result["meets_width"] is True
        assert result["meets_length"] is True
        assert result["meets_minimum"] is True

    def test_narrow_parking(self):
        """Parking too narrow."""
        poly = Polygon([(0, 0), (1.5, 0), (1.5, 6), (0, 6)])  # 1.5m wide
        boundary = Polygon([(-1, -1), (3, -1), (3, 7), (-1, 7)])
        result = validate_parking(poly, boundary, "north", "front")
        assert result["meets_width"] is False

    def test_short_parking(self):
        """Parking too short."""
        poly = Polygon([(0, 0), (3, 0), (3, 3), (0, 3)])  # 3m x 3m
        boundary = Polygon([(-1, -1), (4, -1), (4, 4), (-1, 4)])
        result = validate_parking(poly, boundary, "north", "front")
        assert result["meets_length"] is False


class TestParkingEntityGeneration:
    def test_parking_entity_created(self):
        parking = Polygon([(0, 0), (3, 0), (3, 6), (0, 6)])
        boundary = Polygon([(-1, -1), (4, -1), (4, 7), (-1, 7)])
        polys = {"parking_0": parking}
        types = {"parking_0": "parking"}
        entities = generate_parking_entities(polys, types, boundary, "north", "front")
        assert len(entities) == 1
        assert entities[0]["vehicle_type"] == "car"

    def test_non_parking_rooms_ignored(self):
        room = Polygon([(0, 0), (5, 0), (5, 5), (0, 5)])
        boundary = Polygon([(-1, -1), (6, -1), (6, 6), (-1, 6)])
        polys = {"living_0": room}
        types = {"living_0": "living"}
        entities = generate_parking_entities(polys, types, boundary, "north", "front")
        assert len(entities) == 0
