#!/usr/bin/env python3
"""
Smoke-test script for the eArchitect geometry engine.

Runs the full pipeline using two test cases:
  1. Simple rectangular plot (4 rooms)
  2. Irregular pentagonal plot (5 rooms)
"""
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.layout_generator import generate_layout, handle_dead_spaces
from app.wall_extractor import extract_wall_segments
from app.scorer import score_layout
from app.config import SQ_FT_TO_SQ_M

TEST_CASES = [
    {
        "name": "Rectangular Plot — 3 bedroom house",
        "plot_points": [
            (0, 0), (15, 0), (15, 12), (0, 12)
        ],
        "setback": 1.5,
        "rooms": [
            {"id": "living_0", "type": "living", "min_area_sqm": 150 * SQ_FT_TO_SQ_M, "priority": 10},
            {"id": "kitchen_0", "type": "kitchen", "min_area_sqm": 80 * SQ_FT_TO_SQ_M, "priority": 20},
            {"id": "bedroom_0", "type": "bedroom", "min_area_sqm": 120 * SQ_FT_TO_SQ_M, "priority": 30},
            {"id": "bedroom_1", "type": "bedroom", "min_area_sqm": 120 * SQ_FT_TO_SQ_M, "priority": 30},
            {"id": "toilet_0", "type": "toilet", "min_area_sqm": 40 * SQ_FT_TO_SQ_M, "priority": 40},
        ],
        "preferences": {"parking": False, "ventilation_priority": True},
    },
    {
        "name": "Irregular Pentagonal Plot — 5-room layout",
        "plot_points": [
            (0, 0), (18, 0), (20, 8), (10, 16), (0, 12)
        ],
        "setback": 2.0,
        "rooms": [
            {"id": "living_0", "type": "living", "min_area_sqm": 180 * SQ_FT_TO_SQ_M, "priority": 10},
            {"id": "dining_0", "type": "dining", "min_area_sqm": 100 * SQ_FT_TO_SQ_M, "priority": 15},
            {"id": "kitchen_0", "type": "kitchen", "min_area_sqm": 90 * SQ_FT_TO_SQ_M, "priority": 20},
            {"id": "bedroom_0", "type": "bedroom", "min_area_sqm": 130 * SQ_FT_TO_SQ_M, "priority": 30},
            {"id": "bedroom_1", "type": "bedroom", "min_area_sqm": 130 * SQ_FT_TO_SQ_M, "priority": 30},
            {"id": "bathroom_0", "type": "bathroom", "min_area_sqm": 50 * SQ_FT_TO_SQ_M, "priority": 40},
        ],
        "preferences": {"parking": True, "ventilation_priority": True},
    },
]


def run_test(tc: dict) -> bool:
    print(f"\n{'='*60}")
    print(f"  TEST: {tc['name']}")
    print(f"{'='*60}")

    try:
        result = generate_layout(
            plot_points=tc["plot_points"],
            room_requirements=tc["rooms"],
            setback=tc["setback"],
            preferences=tc["preferences"],
        )

        room_leaves = result["room_leaves"]
        dead_polygons = result["dead_polygons"]
        plot_polygon = result["plot_polygon"]
        inner_polygon = result["inner_polygon"]
        zone_polygons = result["zone_polygons"]

        room_polygon_list = [leaf.polygon for leaf in room_leaves.values() if leaf.room]

        print(f"\n  Plot area      : {plot_polygon.area:.2f} sqm")
        print(f"  Inner area     : {inner_polygon.area:.2f} sqm  (after setback)")
        print(f"  Zones created  : {list(zone_polygons.keys())}")
        print(f"  Rooms placed   : {len(room_polygon_list)}")

        for rid, leaf in room_leaves.items():
            if leaf.room:
                poly = leaf.polygon
                print(
                    f"    [{leaf.room.type:>15}]  id={rid:15}  "
                    f"area={poly.area:.2f} sqm / {poly.area/SQ_FT_TO_SQ_M:.0f} sqft"
                )

        walls = extract_wall_segments(room_polygon_list, plot_polygon, inner_polygon)
        ext_walls = [w for w in walls if w["type"] == "exterior"]
        int_walls = [w for w in walls if w["type"] == "interior"]
        print(f"\n  Walls          : {len(walls)} total"
              f"  ({len(ext_walls)} exterior, {len(int_walls)} interior)")

        dead_list = handle_dead_spaces(dead_polygons)
        print(f"  Dead spaces    : {len(dead_list)}")
        for d in dead_list:
            print(f"    → {d['classification']:12}  {d['area_sqft']:.1f} sqft")

        score = score_layout(room_polygon_list, inner_polygon, zone_polygons)
        print(f"\n  Score breakdown:")
        for k, v in score.items():
            print(f"    {k:<28}: {v:.4f}")

        assert len(room_polygon_list) > 0, "No rooms generated!"
        assert len(walls) > 0, "No walls extracted!"
        assert 0.0 <= score["overall"] <= 1.0, "Score out of range!"

        print(f"\n  [PASSED]")
        return True

    except Exception as exc:
        print(f"\n  [FAILED]: {exc}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    passed = sum(1 for tc in TEST_CASES if run_test(tc))
    print(f"\n{'='*60}")
    print(f"  Results: {passed}/{len(TEST_CASES)} passed")
    print(f"{'='*60}\n")
    sys.exit(0 if passed == len(TEST_CASES) else 1)
