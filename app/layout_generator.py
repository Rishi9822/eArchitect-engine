"""
Backward-compatibility bridge for layout_generator.
Re-exports from app.layout.bsp, app.geometry.setback, and app.config.
"""
from .config import SQ_FT_TO_SQ_M, ZONE_MAP, ZONE_ORDER, ZONE_RATIOS
from .geometry.setback import apply_setback
from .geometry.polygon_utils import compute_longest_axis, split_polygon, aspect_ratio as _aspect_ratio
from .geometry.normalization import ensure_valid as _ensure_valid
from .layout.bsp import (
    RoomSpec,
    BSPNode,
    build_room_specs,
    zone_partition,
    recursive_bsp,
    collect_leaves,
    classify_dead_space,
    generate_bsp_layout,
)


def handle_dead_spaces(leftover_polygons):
    """Legacy dead spaces handler."""
    from .config import SQ_M_TO_SQ_FT
    results = []
    for poly in leftover_polygons:
        if poly.area < 0.5:
            continue
        classification = classify_dead_space(poly)
        coords = [{"x": round(x, 4), "y": round(y, 4)} for x, y in poly.exterior.coords[:-1]]
        results.append({
            "polygon": coords,
            "area_sqft": round(poly.area * SQ_M_TO_SQ_FT, 2),
            "classification": classification,
        })
    return results


def generate_layout(plot_points, room_requirements, setback, preferences):
    """Legacy layout generation pipeline."""
    from shapely.geometry import Polygon
    from .geometry.normalization import normalize_polygon

    plot_polygon = normalize_polygon(plot_points)
    inner_polygon = apply_setback(plot_polygon, setback)
    specs = build_room_specs(room_requirements, preferences)
    result = generate_bsp_layout(inner_polygon, specs)

    return {
        "zone_polygons": result["zone_polygons"],
        "room_leaves": result["room_leaves"],
        "dead_polygons": result["dead_polygons"],
        "plot_polygon": plot_polygon,
        "inner_polygon": inner_polygon,
        "specs": specs,
    }
