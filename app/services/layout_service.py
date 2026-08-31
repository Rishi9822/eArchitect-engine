"""
Layout generation orchestration service.

Full pipeline: validate → generate → architectural elements →
score → optimise → respond.

This is the single entry point that the API routes call.
"""
from __future__ import annotations

import time
import uuid
import logging
from typing import List, Dict, Optional, Any

from shapely.geometry import Polygon

from ..config import (
    ENGINE_VERSION,
    SQ_FT_TO_SQ_M,
    SQ_M_TO_SQ_FT,
    FT_TO_M,
    ZONE_MAP,
    DEAD_SPACE_MIN_AREA_SQM,
    get_room_defaults,
)
from ..models.common import Coordinate
from ..models.input_models import GenerateLayoutRequest
from ..models.output_models import (
    LayoutMetadata,
    PlotOutput,
    BuildableAreaOutput,
    RoomOutput,
    WallSegment,
    DoorOutput,
    WindowOutput,
    EntranceOutput,
    ParkingOutput,
    DeadSpaceOutput,
    CirculationOutput,
    MeasurementsOutput,
    MetricsOutput,
    ScoreBreakdown,
    ValidationItem,
    ValidationOutput,
    CandidateLayout,
    LayoutResponse,
)
from ..geometry.validation import validate_plot_geometry
from ..geometry.normalization import normalize_polygon, poly_to_coord_list
from ..geometry.setback import apply_setback, SetbackError
from ..geometry.polygon_utils import (
    aspect_ratio,
    min_dimension,
    max_dimension,
    polygon_exterior_contact,
)
from ..geometry.measurements import compute_measurements
from ..layout.bsp import (
    RoomSpec,
    build_room_specs,
    generate_bsp_layout,
    classify_dead_space,
)
from ..layout.room_assignment import validate_room_assignment
from ..layout.constraints import check_feasibility
from ..layout.entrance import generate_entrance
from ..layout.doors import generate_doors
from ..layout.windows import generate_windows
from ..layout.parking import generate_parking_entities
from ..layout.circulation import build_adjacency_graph, analyze_circulation
from ..layout.corridor import build_corridor_data
from ..walls.extractor import extract_wall_segments
from ..scoring.scorer import score_layout
from ..optimization.candidates import generate_candidates
from ..optimization.ranking import rank_candidates
from ..api.errors import (
    EngineError,
    InvalidPlotError,
    NoBuildableAreaError,
    LayoutInfeasibleError,
)

logger = logging.getLogger(__name__)


def _poly_to_coords(poly: Polygon) -> List[dict]:
    """Convert polygon exterior to list of {x, y} dicts."""
    return [
        {"x": round(x, 4), "y": round(y, 4)}
        for x, y in list(poly.exterior.coords)[:-1]
    ]


def _build_room_output(
    room_id: str,
    room_type: str,
    zone: str,
    polygon: Polygon,
    inner_polygon: Polygon,
    has_window: bool = False,
) -> dict:
    """Build a room output dict from a polygon."""
    area_sqm = polygon.area
    area_sqft = area_sqm * SQ_M_TO_SQ_FT
    centroid = polygon.centroid
    ext_contact = polygon_exterior_contact(polygon, inner_polygon, min_length=0.3)

    return {
        "id": room_id,
        "type": room_type,
        "area_sqft": round(area_sqft, 2),
        "area_sqm": round(area_sqm, 4),
        "polygon": _poly_to_coords(polygon),
        "centroid": {"x": round(centroid.x, 4), "y": round(centroid.y, 4)},
        "aspect_ratio": round(aspect_ratio(polygon), 3),
        "zone": zone,
        "min_width_m": round(min_dimension(polygon), 3),
        "min_length_m": round(max_dimension(polygon), 3),
        "has_exterior_wall": ext_contact >= 0.3,
        "has_window": has_window,
    }


def _process_single_candidate(
    candidate_result: Dict,
    specs: List[RoomSpec],
    plot_polygon: Polygon,
    inner_polygon: Polygon,
    entrance_config: dict,
    facing: str,
    road_side: str,
    preferences: dict,
    candidate_id: str,
) -> dict:
    """
    Process a single BSP result into a complete candidate layout
    with architectural elements, scoring, and validation.
    """
    timings: Dict[str, float] = {}

    zone_polygons = candidate_result["zone_polygons"]
    room_leaves = candidate_result["room_leaves"]
    dead_polygons = candidate_result["dead_polygons"]
    unplaced = candidate_result.get("unplaced_rooms", [])
    strategy = candidate_result.get("strategy", "open_plan")
    variation = candidate_result.get("variation", "default")
    corridors_data = candidate_result.get("corridors", [])
    corridor_polys = candidate_result.get("corridor_polygons", [])

    # ── Build room data ──────────────────────────────────────────
    room_polygons: Dict[str, Polygon] = {}
    room_types: Dict[str, str] = {}
    room_polygon_list: List[Polygon] = []

    for room_id, leaf in room_leaves.items():
        if leaf.room is None:
            continue
        room_polygons[room_id] = leaf.polygon
        room_types[room_id] = leaf.room.type
        room_polygon_list.append(leaf.polygon)

    # ── Validate room assignments ────────────────────────────────
    t0 = time.perf_counter()
    assignment_validation = validate_room_assignment(
        room_leaves, specs, inner_polygon, strict=False,
    )
    timings["validation_ms"] = (time.perf_counter() - t0) * 1000

    # Build validation output
    validation_warnings = []
    validation_errors = []

    for v in assignment_validation.violations:
        validation_errors.append({
            "code": v.constraint,
            "severity": "error",
            "message": v.message,
            "details": {
                "room_id": v.room_id,
                "required": v.required,
                "actual": v.actual,
            },
        })

    for v in assignment_validation.warnings:
        validation_warnings.append({
            "code": v.constraint,
            "severity": "warning",
            "message": v.message,
            "details": {
                "room_id": v.room_id,
                "required": v.required,
                "actual": v.actual,
            },
        })

    # ── Wall extraction ──────────────────────────────────────────
    t0 = time.perf_counter()
    room_ids_list = list(room_polygons.keys())
    room_polys_list = [room_polygons[rid] for rid in room_ids_list]

    all_polys_for_walls = list(room_polys_list)
    all_ids_for_walls = list(room_ids_list)
    all_polygons_dict = dict(room_polygons)
    all_types_dict = dict(room_types)

    if corridor_polys and corridors_data:
        for corr_data, corr_poly in zip(corridors_data, corridor_polys):
            corr_id = corr_data.get("id", "COR001")
            all_ids_for_walls.append(corr_id)
            all_polys_for_walls.append(corr_poly)
            all_polygons_dict[corr_id] = corr_poly
            all_types_dict[corr_id] = "corridor"

    walls_raw = extract_wall_segments(
        all_polys_for_walls, all_ids_for_walls,
        plot_polygon, inner_polygon,
    )
    timings["wall_extraction_ms"] = (time.perf_counter() - t0) * 1000

    # Helper to resolve wall_id by proximity
    from shapely.geometry import Point as ShapelyPt, LineString as ShapelyLS
    def _find_wall_id(pos_dict: dict) -> Optional[str]:
        pt = ShapelyPt(pos_dict["x"], pos_dict["y"])
        best_id, min_d = None, float("inf")
        for w in walls_raw:
            try:
                l = ShapelyLS([(w["start"]["x"], w["start"]["y"]), (w["end"]["x"], w["end"]["y"])])
                if l.is_empty or not l.is_valid or l.length < 1e-4:
                    continue
                d = l.distance(pt)
                if d < min_d and d < 0.25:
                    min_d = d
                    best_id = w["id"]
            except Exception:
                continue
        return best_id

    # ── Entrance ─────────────────────────────────────────────────
    t0 = time.perf_counter()
    entrance_data = generate_entrance(
        inner_polygon, room_polygons, room_types,
        entrance_config, facing,
    )
    if entrance_data:
        entrance_data["wall_id"] = _find_wall_id(entrance_data["position"])
    timings["entrance_ms"] = (time.perf_counter() - t0) * 1000

    # ── Re-build corridor entities with entrance proximity ────────
    if corridor_polys:
        corridors_data = [
            build_corridor_data(
                c_poly, room_polygons, entrance_data=entrance_data,
                corridor_id=f"corridor_{c_idx}",
            )
            for c_idx, c_poly in enumerate(corridor_polys)
        ]

    # ── Doors ────────────────────────────────────────────────────
    t0 = time.perf_counter()
    entrance_room_id = entrance_data.get("room_id") if entrance_data else None
    doors_raw = generate_doors(all_polygons_dict, all_types_dict, entrance_room_id)
    for d in doors_raw:
        d["wall_id"] = _find_wall_id(d["position"])
    timings["doors_ms"] = (time.perf_counter() - t0) * 1000

    # ── Windows ──────────────────────────────────────────────────
    t0 = time.perf_counter()
    windows_raw = generate_windows(
        room_polygons, room_types, inner_polygon, preferences,
    )
    for win in windows_raw:
        win["wall_id"] = _find_wall_id(win["position"])
    timings["windows_ms"] = (time.perf_counter() - t0) * 1000

    # Track which rooms have windows
    rooms_with_windows = {w["room_id"] for w in windows_raw}

    # ── Parking ──────────────────────────────────────────────────
    parking_entities = generate_parking_entities(
        room_polygons, room_types, inner_polygon, facing, road_side,
    )

    # ── Dead spaces ──────────────────────────────────────────────
    dead_spaces_raw = []
    ds_counter = 1
    for poly in dead_polygons:
        if poly.area < DEAD_SPACE_MIN_AREA_SQM:
            continue
        classification = classify_dead_space(poly)
        dead_spaces_raw.append({
            "id": f"DS{ds_counter:03d}",
            "polygon": _poly_to_coords(poly),
            "area_sqft": round(poly.area * SQ_M_TO_SQ_FT, 2),
            "area_sqm": round(poly.area, 4),
            "classification": classification,
        })
        ds_counter += 1

    # ── Circulation ──────────────────────────────────────────────
    t0 = time.perf_counter()
    graph = build_adjacency_graph(
        room_polygons, doors_raw, entrance_data,
        corridors=corridors_data,
        corridor_polygons=corridor_polys,
    )
    circulation_data = analyze_circulation(
        graph, list(room_polygons.keys()), entrance_room_id,
    )
    timings["circulation_ms"] = (time.perf_counter() - t0) * 1000

    # ── Build room output list ───────────────────────────────────
    rooms_output = []
    for room_id, leaf in room_leaves.items():
        if leaf.room is None:
            continue
        zone = ZONE_MAP.get(leaf.room.type.lower(), "service")
        rooms_output.append(
            _build_room_output(
                room_id, leaf.room.type, zone, leaf.polygon,
                inner_polygon, has_window=room_id in rooms_with_windows,
            )
        )

    # ── Scoring ──────────────────────────────────────────────────
    t0 = time.perf_counter()
    score_data = score_layout(
        room_polygons_dict=room_polygons,
        room_types=room_types,
        room_polygons_list=room_polygon_list,
        plot_polygon=plot_polygon,
        inner_polygon=inner_polygon,
        zone_polygons=zone_polygons,
        windows=windows_raw,
        dead_spaces=dead_spaces_raw,
        parking_entities=parking_entities,
        circulation_data=circulation_data,
        validation_warnings=validation_warnings,
        validation_errors=validation_errors,
    )
    timings["scoring_ms"] = (time.perf_counter() - t0) * 1000

    # ── Measurements ─────────────────────────────────────────────
    measurements_data = compute_measurements(
        plot_polygon, inner_polygon, room_polygon_list,
        walls_raw, doors_raw, windows_raw,
        corridor_polygons=corridor_polys,
    )

    # ── Metrics ──────────────────────────────────────────────────
    total_room_area = sum(p.area for p in room_polygon_list)
    total_corridor_area = sum(c.get("area_sqm", 0.0) for c in corridors_data)
    total_built_up_area = total_room_area + total_corridor_area
    dead_space_area = sum(d["area_sqm"] for d in dead_spaces_raw)

    building_coverage = total_built_up_area / plot_polygon.area if plot_polygon.area > 0 else 0
    buildable_util = total_built_up_area / inner_polygon.area if inner_polygon.area > 0 else 0
    dead_pct = dead_space_area / inner_polygon.area * 100 if inner_polygon.area > 0 else 0

    metrics_data = {
        "building_coverage": round(building_coverage, 4),
        "building_coverage_percentage": round(building_coverage * 100, 2),
        "buildable_utilization": round(buildable_util, 4),
        "buildable_utilization_percentage": round(buildable_util * 100, 2),
        "dead_space_area_sqm": round(dead_space_area, 4),
        "dead_space_area_sqft": round(dead_space_area * SQ_M_TO_SQ_FT, 2),
        "dead_space_percentage": round(dead_pct, 2),
    }

    # ── Validation summary ───────────────────────────────────────
    all_constraints_checked = [
        "ROOM_COMPLETENESS", "ROOM_AREA_MINIMUM", "ROOM_NO_OVERLAP",
        "ROOM_VALID_GEOMETRY", "ROOM_INSIDE_BOUNDARY",
        "ROOM_DIMENSION_MINIMUM", "ROOM_ASPECT_RATIO",
        "NATURAL_LIGHT", "VENTILATION", "PARKING_DIMENSIONS",
    ]

    validation_data = {
        "valid": assignment_validation.valid,
        "warnings": validation_warnings,
        "errors": validation_errors,
        "constraints_checked": all_constraints_checked,
    }

    # Parking warnings
    for p in parking_entities:
        if not p.get("meets_minimum", True):
            validation_warnings.append({
                "code": "PARKING_INFEASIBLE",
                "severity": "warning",
                "message": f"Parking '{p['id']}' does not meet minimum dimensions",
                "details": p,
            })

    # ── Assemble candidate ───────────────────────────────────────
    entrances_output = []
    if entrance_data:
        entrances_output.append(entrance_data)

    return {
        "id": candidate_id,
        "strategy": strategy,
        "variation": variation,
        "rooms": rooms_output,
        "corridors": corridors_data,
        "walls": walls_raw,
        "doors": doors_raw,
        "windows": windows_raw,
        "entrances": entrances_output,
        "parking": parking_entities,
        "dead_spaces": dead_spaces_raw,
        "circulation": circulation_data,
        "measurements": measurements_data,
        "metrics": metrics_data,
        "score": score_data,
        "validation": validation_data,
        "timings": timings,
    }


def generate_layout_response(
    request: GenerateLayoutRequest,
) -> dict:
    """
    Full layout generation pipeline.

    This is the main entry point called by the API route.

    Steps:
    1. Validate plot geometry
    2. Build and apply setback
    3. Expand room requirements
    4. Check feasibility
    5. Generate candidates
    6. Process each candidate (walls, doors, windows, etc.)
    7. Score and rank candidates
    8. Assemble response

    Returns:
        Complete response dict ready for serialisation
    """
    total_start = time.perf_counter()
    timings: Dict[str, float] = {}
    layout_id = f"layout_{uuid.uuid4().hex[:12]}"

    logger.info("Layout request: id=%s", layout_id)

    # ── 1. Validate plot geometry ────────────────────────────────
    t0 = time.perf_counter()
    plot_points = [(p.x, p.y) for p in request.plot.points]
    geo_validation = validate_plot_geometry(plot_points)
    timings["geometry_validation_ms"] = (time.perf_counter() - t0) * 1000

    if not geo_validation.valid:
        errors = geo_validation.errors
        raise InvalidPlotError(
            errors[0]["message"] if errors else "Invalid plot geometry",
            validation_errors=errors,
        )

    # ── 2. Build plot polygon ────────────────────────────────────
    plot_polygon = normalize_polygon(plot_points)

    # ── 3. Apply setback ─────────────────────────────────────────
    t0 = time.perf_counter()
    try:
        inner_polygon = apply_setback(plot_polygon, request.plot.setback)
    except SetbackError as exc:
        raise NoBuildableAreaError(str(exc))
    timings["setback_ms"] = (time.perf_counter() - t0) * 1000

    # ── 4. Expand room requirements ──────────────────────────────
    room_reqs_expanded = []
    for req in request.rooms:
        for i in range(req.count):
            defaults = get_room_defaults(req.type)
            room_reqs_expanded.append({
                "id": f"{req.type}_{i}",
                "type": req.type,
                "min_area_sqm": req.min_area * SQ_FT_TO_SQ_M,
                "min_width_m": (req.min_width or defaults.min_width_ft) * FT_TO_M,
                "min_length_m": (req.min_length or defaults.min_length_ft) * FT_TO_M,
                "preferred_aspect_ratio": req.preferred_aspect_ratio or defaults.preferred_aspect_ratio,
                "max_aspect_ratio": defaults.max_aspect_ratio,
                "priority": req.priority if req.priority is not None else 50,
                "zone": req.zone,
                "requires_exterior_wall": (
                    req.exterior_wall_required
                    if req.exterior_wall_required is not None
                    else defaults.requires_exterior_wall
                ),
            })

    preferences = request.preferences.model_dump() if request.preferences else {}

    specs = build_room_specs(room_reqs_expanded, preferences)

    # ── 5. Check feasibility ─────────────────────────────────────
    feasibility = check_feasibility(specs, inner_polygon)
    if not feasibility.feasible:
        raise LayoutInfeasibleError(
            "; ".join(feasibility.messages),
            required_area_sqft=round(feasibility.required_area_sqm * SQ_M_TO_SQ_FT, 0),
            available_area_sqft=round(feasibility.available_area_sqm * SQ_M_TO_SQ_FT, 0),
            required_rooms=feasibility.required_rooms,
        )

    # ── 6. Generate candidates ───────────────────────────────────
    t0 = time.perf_counter()
    raw_candidates = generate_candidates(
        inner_polygon=inner_polygon,
        specs=specs,
        candidate_count=request.candidate_count,
        seed=request.seed,
        facing=request.plot.facing,
    )
    timings["bsp_generation_ms"] = (time.perf_counter() - t0) * 1000

    # ── 7. Process each candidate ────────────────────────────────
    t0 = time.perf_counter()
    processed_candidates = []

    for idx, raw in enumerate(raw_candidates):
        candidate_id = f"{layout_id}_c{idx}"
        try:
            processed = _process_single_candidate(
                candidate_result=raw,
                specs=specs,
                plot_polygon=plot_polygon,
                inner_polygon=inner_polygon,
                entrance_config=request.entrance.model_dump(),
                facing=request.plot.facing,
                road_side=request.plot.road_side,
                preferences=preferences,
                candidate_id=candidate_id,
            )
            processed_candidates.append(processed)
        except Exception as exc:
            logger.warning("Candidate %d processing failed: %s", idx, exc)

    timings["architectural_elements_ms"] = (time.perf_counter() - t0) * 1000

    if not processed_candidates:
        raise LayoutInfeasibleError(
            "All layout candidates failed processing",
            candidate_count=request.candidate_count,
        )

    # ── 8. Rank candidates ───────────────────────────────────────
    ranked = rank_candidates(
        processed_candidates,
        target_count=request.candidate_count,
    )
    best_id = ranked[0]["id"]

    # ── 9. Assemble response ─────────────────────────────────────
    total_ms = (time.perf_counter() - total_start) * 1000
    timings["total_ms"] = total_ms

    # Plot output
    plot_output = {
        "boundary": _poly_to_coords(plot_polygon),
        "area_sqft": round(plot_polygon.area * SQ_M_TO_SQ_FT, 2),
        "area_sqm": round(plot_polygon.area, 4),
        "facing": request.plot.facing,
        "road_side": request.plot.road_side,
    }

    # Buildable area output
    buildable_output = {
        "boundary": _poly_to_coords(inner_polygon),
        "area_sqft": round(inner_polygon.area * SQ_M_TO_SQ_FT, 2),
        "area_sqm": round(inner_polygon.area, 4),
        "setback_m": request.plot.setback,
    }

    response = {
        "layout": {
            "id": layout_id,
            "version": "1.0",
            "engine_version": ENGINE_VERSION,
            "units": "metric",
            "generation_time_ms": round(total_ms, 2),
        },
        "plot": plot_output,
        "buildable_area": buildable_output,
        "candidates": ranked,
        "best_candidate_id": best_id,
        "timing": timings,
    }

    logger.info(
        "Layout generated: id=%s, candidates=%d, best_score=%.4f, time=%.0fms",
        layout_id, len(ranked),
        ranked[0].get("score", {}).get("overall", 0),
        total_ms,
    )

    return response
