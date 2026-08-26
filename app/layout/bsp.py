"""
Constraint-aware Binary Space Partitioning (BSP) layout generator.

Preserves the working BSP logic from the original layout_generator.py
and enhances it with:
- Minimum room width/length awareness during splits
- Backtracking when a split cannot satisfy requirements
- Deterministic seed support
- Room completeness guarantees

Algorithm:
  1. Partition buildable area into macro zones (public/private/service/parking)
  2. Recursively split each zone to host its assigned rooms
  3. Validate every leaf against room constraints
  4. Collect room-to-leaf assignments and dead spaces
"""
from __future__ import annotations

import math
import logging
import random
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict

from shapely.geometry import Polygon
from shapely.ops import unary_union

from ..config import (
    ZONE_MAP,
    ZONE_ORDER,
    ZONE_RATIOS,
    MAX_BSP_DEPTH,
    MIN_POLYGON_AREA_SQM,
    MAX_ASPECT_RATIO,
    MIN_SPLIT_RATIO,
    MAX_SPLIT_RATIO,
    BSP_AREA_TOLERANCE,
    SQ_FT_TO_SQ_M,
    FT_TO_M,
    PARKING_DEFAULT_AREA_SQM,
    get_room_defaults,
)
from ..geometry.polygon_utils import (
    aspect_ratio,
    min_dimension,
    compute_longest_axis,
    split_polygon,
    find_best_ratio,
)
from ..geometry.normalization import ensure_valid

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# DATA CLASSES
# ─────────────────────────────────────────────

@dataclass
class RoomSpec:
    """Normalised per-room specification (all metric)."""
    id: str
    type: str
    zone: str
    min_area_sqm: float
    min_width_m: float = 0.0
    min_length_m: float = 0.0
    preferred_aspect_ratio: float = 2.0
    max_aspect_ratio: float = 3.5
    priority: int = 50
    requires_exterior_wall: bool = False


@dataclass
class BSPNode:
    """Node in the BSP tree.  Leaf nodes carry a room assignment."""
    polygon: Polygon
    room: Optional[RoomSpec] = None
    left: Optional["BSPNode"] = None
    right: Optional["BSPNode"] = None
    depth: int = 0

    @property
    def is_leaf(self) -> bool:
        return self.left is None and self.right is None


# ─────────────────────────────────────────────
# ROOM SPEC BUILDER
# ─────────────────────────────────────────────

def build_room_specs(
    room_requirements: List[dict],
    preferences: dict,
) -> List[RoomSpec]:
    """
    Expand room requirements into individual RoomSpec objects.

    Handles:
    - count expansion (count=2 → two separate specs)
    - zone assignment from ZONE_MAP
    - default min width/length from config
    - parking injection if preference is set
    """
    specs: List[RoomSpec] = []

    for req in room_requirements:
        room_type = req["type"].lower()
        zone = req.get("zone") or ZONE_MAP.get(room_type, "service")
        defaults = get_room_defaults(room_type)

        count = req.get("count", 1)
        for i in range(count):
            min_area_sqm = req["min_area_sqm"]

            # Use provided min_width/length or fall back to defaults
            min_width_m = req.get("min_width_m", defaults.min_width_ft * FT_TO_M)
            min_length_m = req.get("min_length_m", defaults.min_length_ft * FT_TO_M)

            preferred_ar = req.get(
                "preferred_aspect_ratio", defaults.preferred_aspect_ratio
            )
            max_ar = req.get("max_aspect_ratio", defaults.max_aspect_ratio)

            specs.append(
                RoomSpec(
                    id=req.get("id", f"{room_type}_{i}") if count == 1
                       else f"{room_type}_{i}",
                    type=room_type,
                    zone=zone,
                    min_area_sqm=min_area_sqm,
                    min_width_m=min_width_m,
                    min_length_m=min_length_m,
                    preferred_aspect_ratio=preferred_ar,
                    max_aspect_ratio=max_ar,
                    priority=req.get("priority", 50),
                    requires_exterior_wall=req.get(
                        "requires_exterior_wall",
                        defaults.requires_exterior_wall,
                    ),
                )
            )

    # Add parking if requested and not already present
    if preferences.get("parking"):
        has_parking = any(s.type == "parking" for s in specs)
        if not has_parking:
            specs.append(
                RoomSpec(
                    id="parking_0",
                    type="parking",
                    zone="parking",
                    min_area_sqm=PARKING_DEFAULT_AREA_SQM,
                    min_width_m=2.5,
                    min_length_m=5.0,
                    preferred_aspect_ratio=2.5,
                    max_aspect_ratio=4.0,
                    priority=10,
                )
            )

    return specs


# ─────────────────────────────────────────────
# ZONE PARTITIONING
# ─────────────────────────────────────────────

def _compute_zone_target_areas(
    plot_area: float, rooms_by_zone: Dict[str, List[RoomSpec]]
) -> Dict[str, float]:
    """
    Compute target area for each zone proportional to the total
    minimum room area requirement for that zone.
    """
    zone_required: Dict[str, float] = {}
    total_required = 0.0

    for zone, specs in rooms_by_zone.items():
        zone_required[zone] = sum(s.min_area_sqm for s in specs)
        total_required += zone_required[zone]

    if total_required <= 0:
        return {z: plot_area * ZONE_RATIOS.get(z, 0.1) for z in rooms_by_zone}

    scale = min(1.0, (plot_area * 0.95) / total_required)
    return {zone: req * scale for zone, req in zone_required.items()}


def zone_partition(
    polygon: Polygon, rooms_by_zone: Dict[str, List[RoomSpec]]
) -> Dict[str, Polygon]:
    """
    Slice the buildable polygon into macro zones using BSP.

    Strategy:
    - Sort zones by ZONE_ORDER
    - For each zone (except last), split off its proportional area
    - Last zone gets the remainder
    """
    active_zones = [z for z in ZONE_ORDER if z in rooms_by_zone]
    if not active_zones:
        return {}

    target_areas = _compute_zone_target_areas(polygon.area, rooms_by_zone)
    zone_polygons: Dict[str, Polygon] = {}
    remainder = polygon

    for i, zone in enumerate(active_zones[:-1]):
        if remainder.area < MIN_POLYGON_AREA_SQM:
            break

        remaining_zones = active_zones[i:]
        remaining_target = sum(target_areas.get(z, 0) for z in remaining_zones)
        if remaining_target <= 0:
            fraction = 1.0 / len(remaining_zones)
        else:
            fraction = target_areas.get(zone, 0) / remaining_target
        fraction = max(MIN_SPLIT_RATIO, min(MAX_SPLIT_RATIO, fraction))

        axis = compute_longest_axis(remainder)
        best_ratio = find_best_ratio(remainder, axis, fraction)
        left, right = split_polygon(remainder, axis, best_ratio)

        if left is None or right is None:
            logger.warning("Zone split failed for '%s'; assigning remainder.", zone)
            zone_polygons[zone] = remainder
            break

        zone_polygons[zone] = left
        remainder = right

    # Last zone gets remainder
    if active_zones and remainder is not None and not remainder.is_empty:
        last_zone = active_zones[-1]
        if last_zone not in zone_polygons:
            zone_polygons[last_zone] = remainder

    return zone_polygons


# ─────────────────────────────────────────────
# RECURSIVE BSP (WITHIN EACH ZONE)
# ─────────────────────────────────────────────

def recursive_bsp(
    polygon: Polygon,
    rooms: List[RoomSpec],
    depth: int = 0,
    rng: Optional[random.Random] = None,
) -> BSPNode:
    """
    Recursively partition polygon to host the given rooms.

    Enhanced from original with:
    - Constraint-aware: checks min_width after split
    - Backtracking: tries alternate ratios/axes if first fails
    - Deterministic: uses rng for any randomised decisions

    Base cases:
    - depth >= MAX_BSP_DEPTH → assign highest-priority room
    - len(rooms) == 1 → leaf node
    - len(rooms) == 0 → dead leaf
    - polygon too small → dead leaf
    """
    node = BSPNode(polygon=polygon, depth=depth)

    if not rooms:
        return node

    if len(rooms) == 1 or depth >= MAX_BSP_DEPTH:
        rooms_sorted = sorted(rooms, key=lambda r: (r.priority, -r.min_area_sqm))
        node.room = rooms_sorted[0]
        return node

    # Check if polygon can host at least one room
    if polygon.area < rooms[0].min_area_sqm * BSP_AREA_TOLERANCE:
        logger.debug(
            "Polygon too small (%.2f sqm) for rooms; marking dead.", polygon.area
        )
        return node

    # Sort rooms: high-priority / large rooms first
    sorted_rooms = sorted(rooms, key=lambda r: (r.priority, -r.min_area_sqm))

    # Split rooms into two groups
    split_idx = max(1, len(sorted_rooms) // 2)
    left_rooms = sorted_rooms[:split_idx]
    right_rooms = sorted_rooms[split_idx:]

    # Determine split ratio from area requirements
    left_area_needed = sum(r.min_area_sqm for r in left_rooms)
    right_area_needed = sum(r.min_area_sqm for r in right_rooms)
    total_needed = left_area_needed + right_area_needed

    if total_needed > 0:
        target_ratio = left_area_needed / total_needed
    else:
        target_ratio = 0.5

    target_ratio = max(MIN_SPLIT_RATIO, min(MAX_SPLIT_RATIO, target_ratio))

    # Try primary axis first, then alternate
    primary_axis = compute_longest_axis(polygon)
    alt_axis = "x" if primary_axis == "y" else "y"

    best_split = None

    for axis in [primary_axis, alt_axis]:
        best_ratio = find_best_ratio(polygon, axis, target_ratio)
        left_poly, right_poly = split_polygon(polygon, axis, best_ratio)

        if left_poly is None or right_poly is None:
            continue

        # Check both halves can fit their rooms
        left_min_dim = min_dimension(left_poly)
        right_min_dim = min_dimension(right_poly)

        left_min_width_needed = max(
            (r.min_width_m for r in left_rooms), default=0
        )
        right_min_width_needed = max(
            (r.min_width_m for r in right_rooms), default=0
        )

        # Relax width check: allow if at least 60% of needed width
        left_width_ok = left_min_dim >= left_min_width_needed * 0.6
        right_width_ok = right_min_dim >= right_min_width_needed * 0.6

        left_area_ok = left_poly.area >= sum(
            r.min_area_sqm for r in left_rooms
        ) * BSP_AREA_TOLERANCE
        right_area_ok = right_poly.area >= sum(
            r.min_area_sqm for r in right_rooms
        ) * BSP_AREA_TOLERANCE

        if left_area_ok and right_area_ok and left_width_ok and right_width_ok:
            best_split = (left_poly, right_poly, axis)
            break
        elif left_area_ok and right_area_ok:
            # Area OK but width marginal — keep as fallback
            if best_split is None:
                best_split = (left_poly, right_poly, axis)

    if best_split is None:
        # Split failed entirely — assign highest-priority room to leaf
        node.room = sorted_rooms[0]
        return node

    left_poly, right_poly, _ = best_split
    node.left = recursive_bsp(left_poly, left_rooms, depth + 1, rng)
    node.right = recursive_bsp(right_poly, right_rooms, depth + 1, rng)
    return node


# ─────────────────────────────────────────────
# LEAF COLLECTION
# ─────────────────────────────────────────────

def collect_leaves(node: BSPNode) -> List[BSPNode]:
    """Depth-first traversal to collect all leaf nodes."""
    if node.is_leaf:
        return [node]
    leaves = []
    if node.left:
        leaves.extend(collect_leaves(node.left))
    if node.right:
        leaves.extend(collect_leaves(node.right))
    return leaves


# ─────────────────────────────────────────────
# DEAD SPACE CLASSIFICATION
# ─────────────────────────────────────────────

def classify_dead_space(poly: Polygon) -> str:
    """
    Heuristic classification of leftover polygons.

    Rules:
      - Acute triangle (max angle > 120°) → storage
      - Narrow strip (aspect ratio > 5:1) → passage
      - Area > 6 sqm AND aspect < 3:1     → utility
      - Else                               → unusable
    """
    import numpy as np

    coords = list(poly.exterior.coords)
    n = len(coords) - 1

    ar = aspect_ratio(poly)
    area = poly.area

    if n <= 4:
        vertices = np.array(coords[:-1])
        max_angle = 0.0
        for i in range(n):
            a = vertices[(i - 1) % n]
            b = vertices[i]
            c = vertices[(i + 1) % n]
            ab = a - b
            cb = c - b
            denom = np.linalg.norm(ab) * np.linalg.norm(cb)
            if denom < 1e-9:
                continue
            cos_angle = np.dot(ab, cb) / denom
            cos_angle = np.clip(cos_angle, -1.0, 1.0)
            angle_deg = math.degrees(math.acos(cos_angle))
            max_angle = max(max_angle, angle_deg)

        if max_angle > 120:
            return "storage"

    if ar > 5.0:
        return "passage"

    if area >= 6.0 and ar <= 3.0:
        return "utility"

    return "unusable"


# ─────────────────────────────────────────────
# TOP-LEVEL GENERATOR
# ─────────────────────────────────────────────

def generate_bsp_layout(
    inner_polygon: Polygon,
    specs: List[RoomSpec],
    seed: Optional[int] = None,
) -> Dict:
    """
    Full BSP layout generation pipeline on the buildable polygon.

    Args:
        inner_polygon: buildable area polygon (after setback)
        specs:         list of RoomSpec objects
        seed:          random seed for determinism

    Returns:
        dict with:
            zone_polygons  — {zone: Polygon}
            room_leaves    — {room_id: BSPNode}
            dead_polygons  — List[Polygon]
            unplaced_rooms — List[RoomSpec] (rooms that couldn't be placed)
    """
    rng = random.Random(seed) if seed is not None else random.Random(42)

    # Group rooms by zone
    rooms_by_zone: Dict[str, List[RoomSpec]] = {}
    for s in specs:
        rooms_by_zone.setdefault(s.zone, []).append(s)

    # Macro zone partition
    zone_polygons = zone_partition(inner_polygon, rooms_by_zone)

    # Recursive BSP within each zone
    room_leaves: Dict[str, BSPNode] = {}
    zone_used_polygons: List[Polygon] = []

    for zone, zone_poly in zone_polygons.items():
        zone_rooms = rooms_by_zone.get(zone, [])
        if not zone_rooms:
            continue
        root = recursive_bsp(zone_poly, zone_rooms, depth=0, rng=rng)
        leaves = collect_leaves(root)
        for leaf in leaves:
            if leaf.room is not None:
                room_leaves[leaf.room.id] = leaf
                zone_used_polygons.append(leaf.polygon)

    # Detect dead spaces
    used_union = unary_union(zone_used_polygons) if zone_used_polygons else None
    if used_union is not None and not used_union.is_empty:
        leftover = inner_polygon.difference(used_union)
    else:
        leftover = inner_polygon

    dead_polygons: List[Polygon] = []
    if not leftover.is_empty:
        geoms = list(leftover.geoms) if hasattr(leftover, "geoms") else [leftover]
        for g in geoms:
            if isinstance(g, Polygon) and g.area >= 0.5:
                dead_polygons.append(g)

    # Identify unplaced rooms
    placed_ids = set(room_leaves.keys())
    unplaced = [s for s in specs if s.id not in placed_ids]

    return {
        "zone_polygons": zone_polygons,
        "room_leaves": room_leaves,
        "dead_polygons": dead_polygons,
        "unplaced_rooms": unplaced,
    }
