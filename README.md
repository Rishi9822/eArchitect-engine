# eArchitect Geometry Engine

A standalone computational geometry and architectural layout engine for automated floor-plan generation.

The Engine is the mathematical foundation for the larger **eArchitect SaaS platform**. It accepts plot boundaries, room requirements, entrance preferences, and zoning rules, and produces validated CAD-ready architectural floor plans, wall graphs, window/door placements, circulation connectivity models, quality scores, and estimator-ready geometric measurements.

> **Architectural Boundary**: This repository contains **only** the geometry and layout engine. It does **not** contain UI, frontend frameworks, database connections, authentication, material pricing databases, or estimator cost calculation logic.

---

## Features

- **Plot Geometry Validation**: Comprehensive checks for minimum vertices, self-intersections, non-finite coords, zero-length edges, and orientation.
- **Setback Handling**: Inward buffer calculation with flat/mitre joins and collapse protection.
- **Constraint-Aware Recursive BSP**: Space partitioning that respects minimum room dimensions, areas, and aspect ratios.
- **Room Completeness & Overlap Validation**: Guarantees all requested rooms exist and do not overlap.
- **Enhanced Wall Extraction**: Wall classification (exterior vs. interior), collinear segment merging (eliminates tiny artifacts), wall IDs, and room-to-wall adjacency mapping.
- **Architectural Openings**: Main entrance placement on exterior walls, internal room-to-room doors, and natural light/ventilation window generation.
- **Dedicated Parking Entity**: Specialized dimensional validation (min width/length) and road accessibility analysis.
- **Circulation Analysis**: Graph-based room reachability, BFS connectivity checks, and dead-end penalties.
- **10-Factor Architectural Scoring**:
  - Buildable Utilization
  - Building Coverage
  - Room-Type Aspect Quality
  - Room-Level Adjacency
  - Circulation Efficiency
  - Natural Light Availability
  - Ventilation Exposure
  - Parking Accessibility
  - Dead Space Efficiency
  - Constraint Compliance
- **Estimator-Ready Geometric Measurements**: Dual units (metric `_sqm`/`_m` and imperial `_sqft`/`_ft`) for plot, buildable, room, wall, floor, and roof areas with door/window counts.
- **Multi-Candidate Generation & Ranking**: Generates `balanced`, `compact`, and `zoned` layouts with deterministic seed support.
- **Structured Error Codes**: Clear machine-readable error responses (`INVALID_PLOT`, `NO_BUILDABLE_AREA`, `LAYOUT_INFEASIBLE`, etc.).

---

## Architecture

```
app/
├── main.py                          # FastAPI application factory & startup
├── config.py                        # Centralized constants, defaults & env vars
│
├── api/
│   ├── routes.py                    # Versioned API routes (/api/v1) & compat alias
│   └── errors.py                    # Typed exceptions and JSON error handlers
│
├── models/
│   ├── common.py                    # Coordinate, Point
│   ├── input_models.py              # GenerateLayoutRequest, RoomRequirement, etc.
│   └── output_models.py             # LayoutResponse, CandidateLayout, Measurements, etc.
│
├── geometry/
│   ├── validation.py                # Plot polygon validation
│   ├── normalization.py             # Coordinate snapping & CCW orientation
│   ├── setback.py                   # Inward buffer setback processing
│   ├── polygon_utils.py             # Geometric helpers, splitting, aspect ratios
│   └── measurements.py             # Geometric measurements for estimator
│
├── layout/
│   ├── bsp.py                       # Constraint-aware BSP layout generator
│   ├── room_assignment.py           # Assignment validation & overlap detection
│   ├── constraints.py               # Pre-feasibility checks & hard/soft constraints
│   ├── entrance.py                  # Exterior entrance placement
│   ├── doors.py                     # Internal door generation on shared walls
│   ├── windows.py                   # Window generation on exterior walls
│   ├── parking.py                   # Parking dimensional validation
│   └── circulation.py               # Graph-based circulation model
│
├── walls/
│   └── extractor.py                 # Wall classification, collinear merging, IDs
│
├── scoring/
│   ├── scorer.py                    # 10-factor weighted scoring
│   ├── adjacency.py                 # Room-level adjacency rules & evaluation
│   └── metrics.py                   # Natural light, ventilation, dead-space scoring
│
├── optimization/
│   ├── candidates.py                # Multi-strategy candidate generation
│   └── ranking.py                   # Candidate ranking & selection
│
└── services/
    └── layout_service.py            # End-to-end orchestration pipeline
```

---

## API Endpoints

### 1. Health & Version

- `GET /api/v1/health` — Service health check
- `GET /api/v1/version` — Engine version and API metadata
- `GET /health` — Legacy root health check

### 2. Generate Layout

- `POST /api/v1/layouts/generate` — Primary layout generation endpoint
- `POST /generate-layout` — Backward-compatible alias

#### Request Schema Example

```json
{
  "plot": {
    "points": [
      {"x": 0, "y": 0},
      {"x": 18, "y": 0},
      {"x": 20, "y": 8},
      {"x": 10, "y": 16},
      {"x": 0, "y": 12}
    ],
    "facing": "north",
    "road_side": "front",
    "setback": 2.0
  },
  "rooms": [
    {"type": "living", "count": 1, "min_area": 150, "priority": 10},
    {"type": "dining", "count": 1, "min_area": 100, "priority": 15},
    {"type": "kitchen", "count": 1, "min_area": 80, "priority": 20},
    {"type": "bedroom", "count": 2, "min_area": 120, "priority": 30},
    {"type": "toilet", "count": 1, "min_area": 40, "priority": 40}
  ],
  "entrance": {
    "side": "front",
    "width": 1.2
  },
  "preferences": {
    "parking": true,
    "ventilation_priority": true,
    "natural_light_priority": true
  },
  "candidate_count": 3,
  "seed": 42
}
```

#### Response Structure Summary

```json
{
  "layout": {
    "id": "layout_...",
    "version": "1.0",
    "engine_version": "2.0.0",
    "units": "metric",
    "generation_time_ms": 42.5
  },
  "plot": {
    "boundary": [...],
    "area_sqft": 2228.2,
    "area_sqm": 207.0,
    "facing": "north",
    "road_side": "front"
  },
  "buildable_area": {
    "boundary": [...],
    "area_sqft": 1184.26,
    "area_sqm": 110.02,
    "setback_m": 2.0
  },
  "candidates": [
    {
      "id": "layout_..._c0",
      "strategy": "balanced",
      "rooms": [...],
      "walls": [...],
      "doors": [...],
      "windows": [...],
      "entrances": [...],
      "parking": [...],
      "dead_spaces": [...],
      "circulation": {...},
      "measurements": {
        "plot_area_sqm": 207.0,
        "plot_area_sqft": 2228.2,
        "buildable_area_sqm": 110.02,
        "buildable_area_sqft": 1184.26,
        "room_area_sqm": 110.02,
        "room_area_sqft": 1184.26,
        "built_up_area_sqm": 110.02,
        "built_up_area_sqft": 1184.26,
        "exterior_wall_length_m": 42.5,
        "interior_wall_length_m": 28.1,
        "total_wall_length_m": 70.6,
        "exterior_wall_area_sqm": 127.5,
        "interior_wall_area_sqm": 84.3,
        "floor_area_sqm": 110.02,
        "floor_area_sqft": 1184.26,
        "roof_area_sqm": 110.02,
        "roof_area_sqft": 1184.26,
        "total_door_count": 6,
        "total_window_count": 5,
        "perimeter_m": 42.5
      },
      "metrics": {
        "building_coverage": 0.5315,
        "building_coverage_percentage": 53.15,
        "buildable_utilization": 1.0,
        "buildable_utilization_percentage": 100.0,
        "dead_space_area_sqm": 0.0,
        "dead_space_area_sqft": 0.0,
        "dead_space_percentage": 0.0
      },
      "score": {
        "buildable_utilization": 1.0,
        "building_coverage": 1.0,
        "aspect_quality": 0.92,
        "adjacency": 0.95,
        "circulation": 0.88,
        "natural_light": 1.0,
        "ventilation": 1.0,
        "parking_accessibility": 1.0,
        "dead_space_efficiency": 1.0,
        "constraint_compliance": 1.0,
        "overall": 0.958
      },
      "validation": {
        "valid": true,
        "warnings": [],
        "errors": [],
        "constraints_checked": [...]
      }
    }
  ],
  "best_candidate_id": "layout_..._c0",
  "timing": {...}
}
```

---

## Units & Conventions

- **Internal Geometry**: Metres ($m$, $m^2$).
- **API Inputs**: Room minimum areas are accepted in square feet (`sq_ft`).
- **Conversion Factor**: $1 \text{ sq ft} = 0.092903 \text{ sq m}$.
- **API Outputs**: Areas are explicitly tagged with `_sqm` or `_sqft`, lengths with `_m` or `_ft`.
- **Coordinate System**: Cartesian 2D coordinates $(x, y)$ in metres.

---

## Structured Error Codes

When a request cannot be processed or a layout is impossible, the Engine returns a `422 Unprocessable Entity` with a structured payload:

```json
{
  "error_code": "LAYOUT_INFEASIBLE",
  "message": "Total required area (1500 sqft) exceeds available buildable area (400 sqft).",
  "details": {
    "required_area_sqft": 1500,
    "available_area_sqft": 400,
    "required_rooms": 5
  }
}
```

Common error codes:
- `INVALID_PLOT`: Plot polygon has fewer than 3 vertices, is self-intersecting, or has zero area.
- `INVALID_SETBACK`: Setback value is negative or invalid.
- `NO_BUILDABLE_AREA`: Setback completely eliminates the plot area.
- `ROOM_REQUIREMENT_INVALID`: Room requirement specification is invalid.
- `LAYOUT_INFEASIBLE`: Requested room areas cannot physically fit inside the buildable polygon.
- `GEOMETRY_INVALID`: Internal geometric computation failure.

---

## Local Development & Testing

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run Tests
```bash
pytest tests/ -v
```

### 3. Start Development Server
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Docker & Docker Compose

### Run with Docker Compose
```bash
docker compose up -d --build
```
The Engine will be available at `http://localhost:8001`.

### Build & Run Container Directly
```bash
docker build -t earchitect-engine .
docker run -p 8000:8000 earchitect-engine
```

---

## Estimator Boundary

The Geometry Engine is strictly decoupled from the Estimator module:

```
eArchitect Geometry Engine
        │
        │ Output: Geometry + Geometric Measurements
        ▼
eArchitect Platform
        │
        ▼
Estimator Module (Materials, Pricing, Labor, Rates, Regional Factors)
```