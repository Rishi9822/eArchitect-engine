"""
Tests for setback processing.
"""
import pytest
from shapely.geometry import Polygon
from app.geometry.setback import apply_setback, validate_setback, SetbackError


class TestSetbackApplication:
    def test_zero_setback(self):
        poly = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        result = apply_setback(poly, 0)
        assert abs(result.area - poly.area) < 0.01

    def test_normal_setback(self):
        poly = Polygon([(0, 0), (20, 0), (20, 15), (0, 15)])
        result = apply_setback(poly, 2.0)
        assert result.is_valid
        assert result.area < poly.area
        assert result.area > 0

    def test_small_setback(self):
        poly = Polygon([(0, 0), (10, 0), (10, 8), (0, 8)])
        result = apply_setback(poly, 0.5)
        assert result.is_valid
        assert result.area > 0

    def test_irregular_polygon_setback(self):
        poly = Polygon([(0, 0), (18, 0), (20, 8), (10, 16), (0, 12)])
        result = apply_setback(poly, 2.0)
        assert result.is_valid
        assert result.area > 0


class TestSetbackErrors:
    def test_negative_setback(self):
        poly = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        with pytest.raises(SetbackError):
            apply_setback(poly, -1.0)

    def test_excessive_setback(self):
        """Setback that eliminates the entire plot."""
        poly = Polygon([(0, 0), (4, 0), (4, 4), (0, 4)])  # 16 sqm
        with pytest.raises(SetbackError):
            apply_setback(poly, 5.0)  # Way too large

    def test_setback_collapses_plot(self):
        poly = Polygon([(0, 0), (3, 0), (3, 3), (0, 3)])  # 9 sqm
        with pytest.raises(SetbackError):
            apply_setback(poly, 2.0)  # Leaves < 1 sqm


class TestSetbackValidation:
    def test_feasible_setback(self):
        poly = Polygon([(0, 0), (20, 0), (20, 15), (0, 15)])
        result = validate_setback(poly, 2.0)
        assert result["feasible"] is True
        assert result["estimated_buildable_sqm"] > 0

    def test_infeasible_setback(self):
        poly = Polygon([(0, 0), (3, 0), (3, 3), (0, 3)])
        result = validate_setback(poly, 3.0)
        assert result["feasible"] is False
