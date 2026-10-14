"""
Geometry package — plot validation, normalization, setback, and utilities.
"""
from .validation import validate_plot_geometry, ValidationResult
from .normalization import ensure_valid, normalize_polygon, snap_polygon, poly_to_coord_list
from .setback import apply_setback, validate_setback, SetbackError
from .polygon_utils import (
    aspect_ratio,
    min_dimension,
    max_dimension,
    compute_longest_axis,
    split_polygon,
    find_best_ratio,
    polygon_edges,
    polygons_share_boundary,
    polygon_exterior_contact,
    line_bearing,
    line_orientation,
    get_polygon_internal_angles,
    is_polygon_orthogonal,
    min_polygon_internal_angle,
    compute_inscribed_circle_diameter,
    get_polygon_edge_bearings,
    clip_acute_corners,
)
from .measurements import compute_measurements
from .carpet_area import compute_room_carpet_polygon, compute_layout_carpet_accounting

