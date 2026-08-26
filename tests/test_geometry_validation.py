"""
Tests for plot geometry validation.
"""
import pytest
from app.geometry.validation import validate_plot_geometry


class TestValidPlots:
    def test_valid_rectangle(self):
        pts = [(0, 0), (10, 0), (10, 8), (0, 8)]
        result = validate_plot_geometry(pts)
        assert result.valid is True
        assert len(result.errors) == 0

    def test_valid_pentagon(self):
        pts = [(0, 0), (18, 0), (20, 8), (10, 16), (0, 12)]
        result = validate_plot_geometry(pts)
        assert result.valid is True

    def test_valid_hexagon(self):
        pts = [(5, 0), (10, 0), (13, 5), (10, 10), (5, 10), (2, 5)]
        result = validate_plot_geometry(pts)
        assert result.valid is True

    def test_valid_trapezoid(self):
        pts = [(0, 0), (12, 0), (10, 8), (2, 8)]
        result = validate_plot_geometry(pts)
        assert result.valid is True

    def test_valid_triangle(self):
        pts = [(0, 0), (10, 0), (5, 8)]
        result = validate_plot_geometry(pts)
        assert result.valid is True


class TestInvalidPlots:
    def test_too_few_points(self):
        result = validate_plot_geometry([(0, 0), (1, 1)])
        assert result.valid is False
        assert any(e["code"] == "INVALID_PLOT" for e in result.errors)

    def test_duplicate_points(self):
        result = validate_plot_geometry([(0, 0), (0, 0), (0, 0)])
        assert result.valid is False

    def test_collinear_points(self):
        """Three collinear points produce zero area."""
        result = validate_plot_geometry([(0, 0), (5, 0), (10, 0)])
        assert result.valid is False

    def test_nan_coordinates(self):
        result = validate_plot_geometry([(0, 0), (float("nan"), 5), (5, 0)])
        assert result.valid is False

    def test_inf_coordinates(self):
        result = validate_plot_geometry([(0, 0), (float("inf"), 5), (5, 0)])
        assert result.valid is False

    def test_self_intersecting(self):
        """Bowtie polygon: self-intersecting."""
        result = validate_plot_geometry([(0, 0), (10, 10), (10, 0), (0, 10)])
        assert result.valid is False


class TestWarnings:
    def test_short_edge_warning(self):
        pts = [(0, 0), (10, 0), (10.05, 0.01), (10, 8), (0, 8)]
        result = validate_plot_geometry(pts)
        # Should have a short edge warning
        short_warnings = [w for w in result.warnings if w["code"] == "SHORT_EDGE"]
        assert len(short_warnings) >= 1

    def test_small_plot_warning(self):
        pts = [(0, 0), (1, 0), (1, 1), (0, 1)]  # 1 sqm
        result = validate_plot_geometry(pts)
        small_warnings = [w for w in result.warnings if w["code"] == "SMALL_PLOT"]
        assert len(small_warnings) >= 1
