"""
Priority 10: 20-Plot Test Corpus for Architectural Logic Regression Testing.

Corpus distribution:
1. 5 Rectangular plots (various dimensions, setbacks, orientations, 2BHK/3BHK)
2. 5 L/T-shaped plots (orthogonal non-convex, various corner indents)
3. 5 Irregular Convex plots (pentagons, trapezoids, hexagon with non-90° angles)
4. 5 Irregular Concave plots (including plots with acute internal angles < 75°)
"""
from typing import List, Dict, Any, Optional

CORPUS_20: List[Dict[str, Any]] = [
    # ─────────────────────────────────────────────────────────────
    # Category 1: Rectangular Plots (5)
    # ─────────────────────────────────────────────────────────────
    {
        "id": "rect_20x15_north",
        "category": "rectangular",
        "description": "Standard 20x15m rectangular north-facing plot (3BHK with parking)",
        "request": {
            "plot": {
                "points": [{"x": 0, "y": 0}, {"x": 20, "y": 0}, {"x": 20, "y": 15}, {"x": 0, "y": 15}],
                "facing": "north",
                "road_side": "front",
                "setback": 1.5,
            },
            "rooms": [
                {"type": "living", "count": 1, "min_area": 160},
                {"type": "dining", "count": 1, "min_area": 100},
                {"type": "kitchen", "count": 1, "min_area": 80},
                {"type": "bedroom", "count": 2, "min_area": 120},
                {"type": "toilet", "count": 2, "min_area": 40},
            ],
            "entrance": {"side": "front", "width": 1.2},
            "preferences": {"parking": True, "ventilation_priority": True, "natural_light_priority": True},
            "candidate_count": 2,
            "seed": 42,
        },
    },
    {
        "id": "rect_15x12_east",
        "category": "rectangular",
        "description": "15x12m rectangular east-facing plot (2BHK compact, no parking)",
        "request": {
            "plot": {
                "points": [{"x": 0, "y": 0}, {"x": 15, "y": 0}, {"x": 15, "y": 12}, {"x": 0, "y": 12}],
                "facing": "east",
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
            "preferences": {"parking": False, "ventilation_priority": True, "natural_light_priority": True},
            "candidate_count": 2,
            "seed": 42,
        },
    },
    {
        "id": "rect_18x14_south",
        "category": "rectangular",
        "description": "18x14m rectangular south-facing plot (3BHK with parking)",
        "request": {
            "plot": {
                "points": [{"x": 0, "y": 0}, {"x": 18, "y": 0}, {"x": 18, "y": 14}, {"x": 0, "y": 14}],
                "facing": "south",
                "road_side": "front",
                "setback": 1.5,
            },
            "rooms": [
                {"type": "living", "count": 1, "min_area": 160},
                {"type": "dining", "count": 1, "min_area": 90},
                {"type": "kitchen", "count": 1, "min_area": 80},
                {"type": "bedroom", "count": 2, "min_area": 120},
                {"type": "toilet", "count": 2, "min_area": 40},
            ],
            "entrance": {"side": "front", "width": 1.2},
            "preferences": {"parking": True, "ventilation_priority": True, "natural_light_priority": True},
            "candidate_count": 2,
            "seed": 42,
        },
    },
    {
        "id": "rect_22x16_west",
        "category": "rectangular",
        "description": "22x16m rectangular west-facing plot (large 3BHK with parking, 2m setback)",
        "request": {
            "plot": {
                "points": [{"x": 0, "y": 0}, {"x": 22, "y": 0}, {"x": 22, "y": 16}, {"x": 0, "y": 16}],
                "facing": "west",
                "road_side": "front",
                "setback": 2.0,
            },
            "rooms": [
                {"type": "living", "count": 1, "min_area": 180},
                {"type": "dining", "count": 1, "min_area": 100},
                {"type": "kitchen", "count": 1, "min_area": 80},
                {"type": "bedroom", "count": 3, "min_area": 120},
                {"type": "toilet", "count": 2, "min_area": 40},
            ],
            "entrance": {"side": "front", "width": 1.2},
            "preferences": {"parking": True, "ventilation_priority": True, "natural_light_priority": True},
            "candidate_count": 2,
            "seed": 42,
        },
    },
    {
        "id": "rect_16x10_compact",
        "category": "rectangular",
        "description": "16x10m compact rectangular north-facing plot (2BHK, 1.2m setback)",
        "request": {
            "plot": {
                "points": [{"x": 0, "y": 0}, {"x": 16, "y": 0}, {"x": 16, "y": 10}, {"x": 0, "y": 10}],
                "facing": "north",
                "road_side": "front",
                "setback": 1.2,
            },
            "rooms": [
                {"type": "living", "count": 1, "min_area": 140},
                {"type": "kitchen", "count": 1, "min_area": 75},
                {"type": "bedroom", "count": 2, "min_area": 110},
                {"type": "toilet", "count": 1, "min_area": 35},
            ],
            "entrance": {"side": "front", "width": 1.2},
            "preferences": {"parking": False, "ventilation_priority": True, "natural_light_priority": False},
            "candidate_count": 2,
            "seed": 42,
        },
    },

    # ─────────────────────────────────────────────────────────────
    # Category 2: L/T-Shaped Plots (5)
    # ─────────────────────────────────────────────────────────────
    {
        "id": "l_shape_standard",
        "category": "l_t_shaped",
        "description": "Standard 22x18m L-shaped north-facing plot (cutout at rear right)",
        "request": {
            "plot": {
                "points": [
                    {"x": 0, "y": 0}, {"x": 22, "y": 0}, {"x": 22, "y": 10},
                    {"x": 12, "y": 10}, {"x": 12, "y": 18}, {"x": 0, "y": 18},
                ],
                "facing": "north",
                "road_side": "front",
                "setback": 1.5,
            },
            "rooms": [
                {"type": "living", "count": 1, "min_area": 160},
                {"type": "dining", "count": 1, "min_area": 90},
                {"type": "kitchen", "count": 1, "min_area": 80},
                {"type": "bedroom", "count": 2, "min_area": 120},
                {"type": "toilet", "count": 2, "min_area": 40},
            ],
            "entrance": {"side": "front", "width": 1.2},
            "preferences": {"parking": True, "ventilation_priority": True, "natural_light_priority": True},
            "candidate_count": 2,
            "seed": 42,
        },
    },
    {
        "id": "l_shape_reverse",
        "category": "l_t_shaped",
        "description": "Reverse L-shaped east-facing plot (narrow front wing, wide rear)",
        "request": {
            "plot": {
                "points": [
                    {"x": 0, "y": 0}, {"x": 12, "y": 0}, {"x": 12, "y": 8},
                    {"x": 22, "y": 8}, {"x": 22, "y": 18}, {"x": 0, "y": 18},
                ],
                "facing": "east",
                "road_side": "front",
                "setback": 1.5,
            },
            "rooms": [
                {"type": "living", "count": 1, "min_area": 160},
                {"type": "dining", "count": 1, "min_area": 90},
                {"type": "kitchen", "count": 1, "min_area": 80},
                {"type": "bedroom", "count": 2, "min_area": 120},
                {"type": "toilet", "count": 2, "min_area": 40},
            ],
            "entrance": {"side": "front", "width": 1.2},
            "preferences": {"parking": False, "ventilation_priority": True, "natural_light_priority": True},
            "candidate_count": 2,
            "seed": 42,
        },
    },
    {
        "id": "l_shape_stepped",
        "category": "l_t_shaped",
        "description": "Stepped L-shaped south-facing plot (20x20m envelope)",
        "request": {
            "plot": {
                "points": [
                    {"x": 0, "y": 0}, {"x": 20, "y": 0}, {"x": 20, "y": 12},
                    {"x": 10, "y": 12}, {"x": 10, "y": 20}, {"x": 0, "y": 20},
                ],
                "facing": "south",
                "road_side": "front",
                "setback": 1.5,
            },
            "rooms": [
                {"type": "living", "count": 1, "min_area": 160},
                {"type": "dining", "count": 1, "min_area": 90},
                {"type": "kitchen", "count": 1, "min_area": 80},
                {"type": "bedroom", "count": 2, "min_area": 120},
                {"type": "toilet", "count": 2, "min_area": 40},
            ],
            "entrance": {"side": "front", "width": 1.2},
            "preferences": {"parking": True, "ventilation_priority": True, "natural_light_priority": True},
            "candidate_count": 2,
            "seed": 42,
        },
    },
    {
        "id": "t_shape_north",
        "category": "l_t_shaped",
        "description": "T-shaped north-facing plot (stem at front road, crossbar at rear)",
        "request": {
            "plot": {
                "points": [
                    {"x": 4, "y": 0}, {"x": 18, "y": 0}, {"x": 18, "y": 8},
                    {"x": 22, "y": 8}, {"x": 22, "y": 18}, {"x": 0, "y": 18},
                    {"x": 0, "y": 8}, {"x": 4, "y": 8},
                ],
                "facing": "north",
                "road_side": "front",
                "setback": 1.5,
            },
            "rooms": [
                {"type": "living", "count": 1, "min_area": 160},
                {"type": "dining", "count": 1, "min_area": 90},
                {"type": "kitchen", "count": 1, "min_area": 80},
                {"type": "bedroom", "count": 2, "min_area": 120},
                {"type": "toilet", "count": 2, "min_area": 40},
            ],
            "entrance": {"side": "front", "width": 1.2},
            "preferences": {"parking": False, "ventilation_priority": True, "natural_light_priority": True},
            "candidate_count": 2,
            "seed": 42,
        },
    },
    {
        "id": "t_shape_wide",
        "category": "l_t_shaped",
        "description": "Wide T-shaped south-facing plot (broad front road facade, centered rear projection)",
        "request": {
            "plot": {
                "points": [
                    {"x": 0, "y": 0}, {"x": 24, "y": 0}, {"x": 24, "y": 8},
                    {"x": 18, "y": 8}, {"x": 18, "y": 18}, {"x": 6, "y": 18},
                    {"x": 6, "y": 8}, {"x": 0, "y": 8},
                ],
                "facing": "south",
                "road_side": "front",
                "setback": 1.5,
            },
            "rooms": [
                {"type": "living", "count": 1, "min_area": 160},
                {"type": "dining", "count": 1, "min_area": 90},
                {"type": "kitchen", "count": 1, "min_area": 80},
                {"type": "bedroom", "count": 2, "min_area": 120},
                {"type": "toilet", "count": 2, "min_area": 40},
            ],
            "entrance": {"side": "front", "width": 1.2},
            "preferences": {"parking": True, "ventilation_priority": True, "natural_light_priority": True},
            "candidate_count": 2,
            "seed": 42,
        },
    },

    # ─────────────────────────────────────────────────────────────
    # Category 3: Irregular Convex Plots (5)
    # ─────────────────────────────────────────────────────────────
    {
        "id": "pentagon_standard",
        "category": "irregular_convex",
        "description": "Standard pentagonal convex plot with slanted rear boundary",
        "request": {
            "plot": {
                "points": [
                    {"x": 0, "y": 0}, {"x": 18, "y": 0}, {"x": 20, "y": 8},
                    {"x": 10, "y": 16}, {"x": 0, "y": 12},
                ],
                "facing": "north",
                "road_side": "front",
                "setback": 1.5,
            },
            "rooms": [
                {"type": "living", "count": 1, "min_area": 150},
                {"type": "dining", "count": 1, "min_area": 90},
                {"type": "kitchen", "count": 1, "min_area": 80},
                {"type": "bedroom", "count": 2, "min_area": 120},
                {"type": "toilet", "count": 1, "min_area": 40},
            ],
            "entrance": {"side": "front", "width": 1.2},
            "preferences": {"parking": True, "ventilation_priority": True, "natural_light_priority": True},
            "candidate_count": 2,
            "seed": 42,
        },
    },
    {
        "id": "pentagon_shallow",
        "category": "irregular_convex",
        "description": "Shallow pentagonal convex plot (20m front, 18m depth)",
        "request": {
            "plot": {
                "points": [
                    {"x": 0, "y": 0}, {"x": 20, "y": 0}, {"x": 22, "y": 10},
                    {"x": 12, "y": 18}, {"x": 0, "y": 15},
                ],
                "facing": "north",
                "road_side": "front",
                "setback": 1.5,
            },
            "rooms": [
                {"type": "living", "count": 1, "min_area": 160},
                {"type": "dining", "count": 1, "min_area": 90},
                {"type": "kitchen", "count": 1, "min_area": 80},
                {"type": "bedroom", "count": 2, "min_area": 120},
                {"type": "toilet", "count": 2, "min_area": 40},
            ],
            "entrance": {"side": "front", "width": 1.2},
            "preferences": {"parking": True, "ventilation_priority": True, "natural_light_priority": True},
            "candidate_count": 2,
            "seed": 42,
        },
    },
    {
        "id": "trapezoid_wide_front",
        "category": "irregular_convex",
        "description": "Trapezoid plot with 24m wide front and 14m rear",
        "request": {
            "plot": {
                "points": [
                    {"x": 0, "y": 0}, {"x": 24, "y": 0}, {"x": 19, "y": 16},
                    {"x": 5, "y": 16},
                ],
                "facing": "north",
                "road_side": "front",
                "setback": 1.5,
            },
            "rooms": [
                {"type": "living", "count": 1, "min_area": 160},
                {"type": "dining", "count": 1, "min_area": 90},
                {"type": "kitchen", "count": 1, "min_area": 80},
                {"type": "bedroom", "count": 2, "min_area": 120},
                {"type": "toilet", "count": 2, "min_area": 40},
            ],
            "entrance": {"side": "front", "width": 1.2},
            "preferences": {"parking": True, "ventilation_priority": True, "natural_light_priority": True},
            "candidate_count": 2,
            "seed": 42,
        },
    },
    {
        "id": "trapezoid_narrow_front",
        "category": "irregular_convex",
        "description": "Trapezoid plot with 14m front widening to 22m rear",
        "request": {
            "plot": {
                "points": [
                    {"x": 4, "y": 0}, {"x": 18, "y": 0}, {"x": 22, "y": 16},
                    {"x": 0, "y": 16},
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
            "preferences": {"parking": False, "ventilation_priority": True, "natural_light_priority": True},
            "candidate_count": 2,
            "seed": 42,
        },
    },
    {
        "id": "convex_hexagon",
        "category": "irregular_convex",
        "description": "Convex hexagonal plot with 6 chamfered edges",
        "request": {
            "plot": {
                "points": [
                    {"x": 4, "y": 0}, {"x": 18, "y": 0}, {"x": 22, "y": 8},
                    {"x": 18, "y": 16}, {"x": 4, "y": 16}, {"x": 0, "y": 8},
                ],
                "facing": "north",
                "road_side": "front",
                "setback": 1.5,
            },
            "rooms": [
                {"type": "living", "count": 1, "min_area": 160},
                {"type": "dining", "count": 1, "min_area": 90},
                {"type": "kitchen", "count": 1, "min_area": 80},
                {"type": "bedroom", "count": 2, "min_area": 120},
                {"type": "toilet", "count": 2, "min_area": 40},
            ],
            "entrance": {"side": "front", "width": 1.2},
            "preferences": {"parking": True, "ventilation_priority": True, "natural_light_priority": True},
            "candidate_count": 2,
            "seed": 42,
        },
    },

    # ─────────────────────────────────────────────────────────────
    # Category 4: Irregular Concave Plots (<75° angle) (5)
    # ─────────────────────────────────────────────────────────────
    {
        "id": "concave_acute_corner",
        "category": "irregular_concave",
        "description": "Irregular concave plot with acute corner (49.4° internal angle)",
        "request": {
            "plot": {
                "points": [
                    {"x": 0, "y": 0}, {"x": 22, "y": 0}, {"x": 16, "y": 7},
                    {"x": 20, "y": 16}, {"x": 0, "y": 16},
                ],
                "facing": "north",
                "road_side": "front",
                "setback": 1.5,
            },
            "rooms": [
                {"type": "living", "count": 1, "min_area": 150},
                {"type": "dining", "count": 1, "min_area": 90},
                {"type": "kitchen", "count": 1, "min_area": 80},
                {"type": "bedroom", "count": 2, "min_area": 110},
                {"type": "toilet", "count": 1, "min_area": 40},
            ],
            "entrance": {"side": "front", "width": 1.2},
            "preferences": {"parking": True, "ventilation_priority": True, "natural_light_priority": True},
            "candidate_count": 2,
            "seed": 42,
        },
    },
    {
        "id": "concave_side_indent",
        "category": "irregular_concave",
        "description": "Concave plot with angular side indentation notch",
        "request": {
            "plot": {
                "points": [
                    {"x": 0, "y": 0}, {"x": 22, "y": 0}, {"x": 22, "y": 7},
                    {"x": 15, "y": 10}, {"x": 22, "y": 13}, {"x": 22, "y": 18},
                    {"x": 0, "y": 18},
                ],
                "facing": "north",
                "road_side": "front",
                "setback": 1.5,
            },
            "rooms": [
                {"type": "living", "count": 1, "min_area": 160},
                {"type": "dining", "count": 1, "min_area": 90},
                {"type": "kitchen", "count": 1, "min_area": 80},
                {"type": "bedroom", "count": 2, "min_area": 120},
                {"type": "toilet", "count": 2, "min_area": 40},
            ],
            "entrance": {"side": "front", "width": 1.2},
            "preferences": {"parking": True, "ventilation_priority": True, "natural_light_priority": True},
            "candidate_count": 2,
            "seed": 42,
        },
    },
    {
        "id": "concave_l_notch",
        "category": "irregular_concave",
        "description": "Irregular concave plot with diagonal cut notch (73.3° angle)",
        "request": {
            "plot": {
                "points": [
                    {"x": 0, "y": 0}, {"x": 22, "y": 0}, {"x": 22, "y": 10},
                    {"x": 12, "y": 7}, {"x": 14, "y": 18}, {"x": 0, "y": 18},
                ],
                "facing": "north",
                "road_side": "front",
                "setback": 1.5,
            },
            "rooms": [
                {"type": "living", "count": 1, "min_area": 150},
                {"type": "dining", "count": 1, "min_area": 90},
                {"type": "kitchen", "count": 1, "min_area": 80},
                {"type": "bedroom", "count": 2, "min_area": 110},
                {"type": "toilet", "count": 2, "min_area": 40},
            ],
            "entrance": {"side": "front", "width": 1.2},
            "preferences": {"parking": True, "ventilation_priority": True, "natural_light_priority": True},
            "candidate_count": 2,
            "seed": 42,
        },
    },
    {
        "id": "concave_rear_cut",
        "category": "irregular_concave",
        "description": "Concave plot with triangular rear cut (59.0° angle)",
        "request": {
            "plot": {
                "points": [
                    {"x": 0, "y": 0}, {"x": 20, "y": 0}, {"x": 20, "y": 18},
                    {"x": 10, "y": 12}, {"x": 0, "y": 18},
                ],
                "facing": "north",
                "road_side": "front",
                "setback": 1.5,
            },
            "rooms": [
                {"type": "living", "count": 1, "min_area": 150},
                {"type": "dining", "count": 1, "min_area": 90},
                {"type": "kitchen", "count": 1, "min_area": 80},
                {"type": "bedroom", "count": 2, "min_area": 110},
                {"type": "toilet", "count": 2, "min_area": 40},
            ],
            "entrance": {"side": "front", "width": 1.2},
            "preferences": {"parking": True, "ventilation_priority": True, "natural_light_priority": True},
            "candidate_count": 2,
            "seed": 42,
        },
    },
    {
        "id": "concave_courtyard",
        "category": "irregular_concave",
        "description": "Concave plot with angular courtyard indentation (24x18m envelope)",
        "request": {
            "plot": {
                "points": [
                    {"x": 0, "y": 0}, {"x": 24, "y": 0}, {"x": 24, "y": 18},
                    {"x": 17, "y": 18}, {"x": 15, "y": 10}, {"x": 9, "y": 10},
                    {"x": 7, "y": 18}, {"x": 0, "y": 18},
                ],
                "facing": "north",
                "road_side": "front",
                "setback": 1.5,
            },
            "rooms": [
                {"type": "living", "count": 1, "min_area": 160},
                {"type": "dining", "count": 1, "min_area": 90},
                {"type": "kitchen", "count": 1, "min_area": 80},
                {"type": "bedroom", "count": 2, "min_area": 120},
                {"type": "toilet", "count": 2, "min_area": 40},
            ],
            "entrance": {"side": "front", "width": 1.2},
            "preferences": {"parking": True, "ventilation_priority": True, "natural_light_priority": True},
            "candidate_count": 2,
            "seed": 42,
        },
    },
]


def get_corpus() -> List[Dict[str, Any]]:
    """Return all 20 plots in the regression corpus."""
    return CORPUS_20


def get_corpus_by_category(category: str) -> List[Dict[str, Any]]:
    """Return plots matching the specified category."""
    return [p for p in CORPUS_20 if p["category"] == category]


def get_plot_by_id(plot_id: str) -> Optional[Dict[str, Any]]:
    """Return a single plot from the corpus by its ID."""
    for p in CORPUS_20:
        if p["id"] == plot_id:
            return p
    return None
