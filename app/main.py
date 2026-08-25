"""
FastAPI entrypoint for the eArchitect Geometry Engine.

Runs on: http://localhost:8000
Primary endpoint: POST /generate-layout

Unit conventions (internal):
  All polygon coordinates in METRES.
  Input from client may be in sq-ft for area requirements — converted here.

1 sq-ft = 0.0929 sq-m
"""
from __future__ import annotations

import logging
import uuid
import math
from typing import List

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from shapely.geometry import Polygon

from .models import (
    GenerateLayoutRequest,
    LayoutResponse,
    RoomOutput,
    WallSegment,
    DeadSpaceOutput,
    Coordinate,
    ScoreBreakdown,
)
from .layout_generator import generate_layout, handle_dead_spaces, SQ_FT_TO_SQ_M, ZONE_MAP
from .wall_extractor import extract_wall_segments
from .scorer import score_layout

# ─────────────────────────────────────────────
# APPLICATION SETUP
# ─────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="eArchitect Geometry Engine",
    description=(
        "Computational geometry backend for AI-Based Automated Floor Plan Generation. "
        "Implements Recursive Binary Space Partitioning (BSP) to generate "
        "architectural floor plans from irregular plot polygons."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _poly_to_coords(poly: Polygon) -> List[Coordinate]:
    """Convert Shapely Polygon exterior ring to list of Coordinate models."""
    return [
        Coordinate(x=round(x, 4), y=round(y, 4))
        for x, y in list(poly.exterior.coords)[:-1]  # exclude repeated last point
    ]


def _aspect_ratio(poly: Polygon) -> float:
    """Bounding-box aspect ratio (always ≥ 1.0)."""
    try:
        minx, miny, maxx, maxy = poly.minimum_rotated_rectangle.bounds
    except Exception:
        minx, miny, maxx, maxy = poly.bounds
    w, h = maxx - minx, maxy - miny
    if min(w, h) < 1e-6:
        return 999.0
    return round(max(w, h) / min(w, h), 3)


def _build_room_output(
    room_id: str,
    room_type: str,
    zone: str,
    polygon: Polygon,
) -> RoomOutput:
    """Format a room polygon as a structured RoomOutput model."""
    area_sqm = polygon.area
    area_sqft = area_sqm / SQ_FT_TO_SQ_M
    centroid = polygon.centroid

    return RoomOutput(
        id=room_id,
        type=room_type,
        area_sqft=round(area_sqft, 2),
        area_sqm=round(area_sqm, 4),
        polygon=_poly_to_coords(polygon),
        centroid=Coordinate(x=round(centroid.x, 4), y=round(centroid.y, 4)),
        aspect_ratio=_aspect_ratio(polygon),
        zone=zone,
    )


# ─────────────────────────────────────────────
# HEALTH CHECK
# ─────────────────────────────────────────────

@app.get("/", tags=["health"])
def root():
    return {"status": "ok", "service": "eArchitect Geometry Engine", "version": "1.0.0"}


@app.get("/health", tags=["health"])
def health():
    return {"status": "healthy"}


# ─────────────────────────────────────────────
# MAIN ENDPOINT
# ─────────────────────────────────────────────

@app.post(
    "/generate-layout",
    response_model=LayoutResponse,
    tags=["layout"],
    summary="Generate floor plan layout using BSP",
    description=(
        "Accepts an irregular plot polygon, room requirements, entrance config, "
        "and user preferences. Returns a classified wall graph, room polygons, "
        "dead space regions, and a quality score."
    ),
)
def generate_layout_endpoint(request: GenerateLayoutRequest):
    try:
        logger.info(
            "Layout request: %d rooms, setback=%.1fm, facing=%s",
            sum(r.count for r in request.rooms),
            request.plot.setback,
            request.plot.facing,
        )

        # ── 1. Convert plot points to (x, y) tuples ──────────────────────────
        plot_points = [(p.x, p.y) for p in request.plot.points]

        # ── 2. Expand room requirements (count > 1 = multiple instances) ─────
        room_specs_raw: List[dict] = []
        for req in request.rooms:
            for i in range(req.count):
                room_specs_raw.append({
                    "id": f"{req.type}_{i}",
                    "type": req.type,
                    "min_area_sqm": req.min_area * SQ_FT_TO_SQ_M,  # sq-ft → sq-m
                    "priority": req.priority if req.priority is not None else 50,
                })

        # ── 3. Run BSP layout generation ──────────────────────────────────────
        result = generate_layout(
            plot_points=plot_points,
            room_requirements=room_specs_raw,
            setback=request.plot.setback,
            preferences=request.preferences.model_dump(),
        )

        zone_polygons   = result["zone_polygons"]
        room_leaves     = result["room_leaves"]
        dead_polygons   = result["dead_polygons"]
        plot_polygon    = result["plot_polygon"]
        inner_polygon   = result["inner_polygon"]

        # ── 4. Build room output list ─────────────────────────────────────────
        rooms_output: List[RoomOutput] = []
        room_polygon_list = []

        for room_id, leaf in room_leaves.items():
            room_spec = leaf.room
            if room_spec is None:
                continue
            zone = ZONE_MAP.get(room_spec.type.lower(), "service")
            room_out = _build_room_output(
                room_id=room_spec.id,
                room_type=room_spec.type,
                zone=zone,
                polygon=leaf.polygon,
            )
            rooms_output.append(room_out)
            room_polygon_list.append(leaf.polygon)

        if not rooms_output:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Layout generation produced no rooms. "
                    "The plot may be too small for the given room requirements and setback."
                ),
            )

        # ── 5. Extract wall segments ───────────────────────────────────────────
        raw_walls = extract_wall_segments(room_polygon_list, plot_polygon, inner_polygon)
        walls_output: List[WallSegment] = [
            WallSegment(
                start=Coordinate(**w["start"]),
                end=Coordinate(**w["end"]),
                type=w["type"],
                thickness=w["thickness"],
                length=w["length"],
            )
            for w in raw_walls
        ]

        # ── 6. Handle dead spaces ─────────────────────────────────────────────
        dead_raw = handle_dead_spaces(dead_polygons)
        dead_output: List[DeadSpaceOutput] = [
            DeadSpaceOutput(
                polygon=[Coordinate(**c) for c in d["polygon"]],
                area_sqft=d["area_sqft"],
                classification=d["classification"],
            )
            for d in dead_raw
        ]

        # ── 7. Score the layout ───────────────────────────────────────────────
        score_data = score_layout(
            room_polygons=room_polygon_list,
            inner_polygon=inner_polygon,
            zone_polygons=zone_polygons,
        )

        # ── 8. Build response ─────────────────────────────────────────────────
        plot_area_sqft = plot_polygon.area / SQ_FT_TO_SQ_M
        used_area_sqft = sum(r.area_sqft for r in rooms_output)

        response = LayoutResponse(
            rooms=rooms_output,
            walls=walls_output,
            dead_spaces=dead_output,
            score=score_data["overall"],
            score_breakdown=ScoreBreakdown(
                space_utilization=score_data["space_utilization"],
                aspect_ratio_quality=score_data["aspect_ratio_quality"],
                adjacency_correctness=score_data["adjacency_correctness"],
                circulation_efficiency=score_data["circulation_efficiency"],
                overall=score_data["overall"],
            ),
            plot_area_sqft=round(plot_area_sqft, 2),
            used_area_sqft=round(used_area_sqft, 2),
            setback_applied=request.plot.setback,
        )

        logger.info(
            "Layout generated successfully: %d rooms, %d walls, %d dead spaces, score=%.3f",
            len(rooms_output), len(walls_output), len(dead_output), score_data["overall"],
        )
        return response

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unhandled error in layout generation")
        raise HTTPException(status_code=500, detail=f"Geometry engine error: {str(exc)}")


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
