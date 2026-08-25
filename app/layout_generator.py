"""
Core Recursive Binary Space Partitioning (BSP) Layout Generator.

Algorithm:
  1. Apply setback to plot polygon (inward buffer).
  2. Partition full plot into 3 macro zones:
     - public  (living, dining)
     - private (bedrooms, study)
     - service (kitchen, toilet, bathroom)
  3. Recursively slice each zone polygon using the longest-axis strategy
     until leaf nodes can hold exactly one room.
  4. Assign rooms to leaf polygons by area proximity.
  5. Classify remaining fragments as dead space.

All units: meters (internally). sq-ft conversions at output boundary.
1 sq-ft = 0.0929 sq-m
"""
from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict

import numpy as np
from shapely.geometry import Polygon, LineString, MultiPolygon, Point as ShapelyPoint
from shapely.ops import split, unary_union
from shapely.validation import make_valid

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────

SQ_FT_TO_SQ_M = 0.0929          # 1 sq ft in sq metres
MAX_BSP_DEPTH = 10               # Guard against infinite recursion
MIN_POLYGON_AREA_SQM = 1.0       # Ignore fragments smaller than 1 sqm
MAX_ASPECT_RATIO = 4.0           # Reject splits producing rooms > 4:1 ratio
MIN_SPLIT_RATIO = 0.25           # Never split closer than 25% from edge
MAX_SPLIT_RATIO = 0.75

# Zone membership rules
ZONE_MAP: Dict[str, str] = {
    "living": "public",
    "dining": "public",
    "foyer": "public",
    "lobby": "public",
    "bedroom": "private",
    "master_bedroom": "private",
    "study": "private",
    "dressing": "private",
    "kitchen": "service",
    "toilet": "service",
    "bathroom": "service",
    "utility": "service",
    "store": "service",
    "parking": "parking",
}

ZONE_ORDER = ["public", "private", "service", "parking"]

# Approximate zone area ratios (tunable)
ZONE_RATIOS: Dict[str, float] = {
    "public": 0.35,
    "private": 0.40,
    "service": 0.18,
    "parking": 0.07,
}


# ─────────────────────────────────────────────
# DATA CLASSES
# ─────────────────────────────────────────────

@dataclass
class RoomSpec:
    """Normalised per-room specification."""
    id: str
    type: str
    zone: str
    min_area_sqm: float
    priority: int = 0


@dataclass
class BSPNode:
    """Node in the BSP tree. Leaf nodes carry a room assignment."""
    polygon: Polygon
    room: Optional[RoomSpec] = None
    left: Optional["BSPNode"] = None
    right: Optional["BSPNode"] = None
    depth: int = 0

    @property
    def is_leaf(self) -> bool:
        return self.left is None and self.right is None


# ─────────────────────────────────────────────
# GEOMETRY UTILITIES
# ─────────────────────────────────────────────

def _ensure_valid(poly: Polygon) -> Polygon:
    """Return a valid, non-degenerate Shapely Polygon."""
    if not poly.is_valid:
        poly = make_valid(poly)
    if poly.is_empty or poly.area < 1e-6:
        raise ValueError("Degenerate polygon after validation")
    # make_valid can return GeometryCollection — extract largest polygon
    if isinstance(poly, MultiPolygon):
        poly = max(poly.geoms, key=lambda g: g.area)
    return poly


def apply_setback(polygon: Polygon, distance: float) -> Polygon:
    """
    Inward buffer (negative offset) to apply building setback lines.
    Uses Shapely's buffer with join_style=2 (flat/mitre) for clean corners.
    """
    if distance <= 0:
        return polygon
    buffered = polygon.buffer(-distance, join_style=2, mitre_limit=5.0)
    if buffered.is_empty or buffered.area < MIN_POLYGON_AREA_SQM:
        logger.warning(
            "Setback of %.2fm collapses plot (area %.2f sqm). "
            "Reducing setback to half.", distance, polygon.area
        )
        buffered = polygon.buffer(-distance * 0.5, join_style=2, mitre_limit=5.0)
    return _ensure_valid(buffered)


def compute_longest_axis(polygon: Polygon) -> str:
    """
    Determine dominant split axis from the oriented bounding box.

    Returns:
        'x' — split with a horizontal line (cuts top/bottom halves)
        'y' — split with a vertical line   (cuts left/right halves)
    """
    minx, miny, maxx, maxy = polygon.bounds
    width = maxx - minx
    height = maxy - miny
    return "y" if width > height else "x"


def _build_split_line(polygon: Polygon, axis: str, ratio: float) -> LineString:
    """
    Build an infinite-span LineString that bisects the polygon's bounding
    box at the given ratio along the chosen axis.

    axis='y' → vertical split at x = minx + ratio*(maxx-minx)
    axis='x' → horizontal split at y = miny + ratio*(maxy-miny)
    """
    minx, miny, maxx, maxy = polygon.bounds
    # Extend line well beyond polygon to guarantee full split
    pad = max(maxx - minx, maxy - miny) * 2

    if axis == "y":
        split_x = minx + ratio * (maxx - minx)
        return LineString([(split_x, miny - pad), (split_x, maxy + pad)])
    else:
        split_y = miny + ratio * (maxy - miny)
        return LineString([(minx - pad, split_y), (maxx + pad, split_y)])


def split_polygon(
    polygon: Polygon, axis: str, ratio: float
) -> Tuple[Optional[Polygon], Optional[Polygon]]:
    """
    Split a polygon along the given axis at the given ratio.

    Returns two polygons (left/bottom, right/top) or (None, None) on failure.

    Uses shapely.ops.split — requires the LineString to cross the polygon.
    """
    try:
        line = _build_split_line(polygon, axis, ratio)
        result = split(polygon, line)

        # Collect non-degenerate polygons
        parts = [
            g for g in result.geoms
            if isinstance(g, Polygon) and g.area >= MIN_POLYGON_AREA_SQM
        ]

        if len(parts) < 2:
            return None, None

        # Sort by coordinate (left→right or bottom→top) so ordering is deterministic
        if axis == "y":
            parts.sort(key=lambda g: g.centroid.x)
        else:
            parts.sort(key=lambda g: g.centroid.y)

        # Merge any extra fragments with nearest part
        if len(parts) > 2:
            left = unary_union(parts[: len(parts) // 2])
            right = unary_union(parts[len(parts) // 2 :])
            parts = [left, right]

        return _ensure_valid(parts[0]), _ensure_valid(parts[1])

    except Exception as exc:
        logger.debug("split_polygon failed: %s", exc)
        return None, None


def _aspect_ratio(poly: Polygon) -> float:
    """Bounding-box aspect ratio (always ≥ 1)."""
    minx, miny, maxx, maxy = poly.bounds
    w, h = maxx - minx, maxy - miny
    if min(w, h) < 1e-6:
        return float("inf")
    return max(w, h) / min(w, h)


def _find_best_ratio(polygon: Polygon, axis: str, target_ratio: float) -> float:
    """
    Attempt ratios near `target_ratio` and return the first that produces
    two valid polygons with acceptable aspect ratios.
    """
    candidates = [target_ratio]
    step = 0.05
    for delta in [0, step, -step, step * 2, -step * 2, step * 3, -step * 3]:
        r = target_ratio + delta
        if MIN_SPLIT_RATIO <= r <= MAX_SPLIT_RATIO:
            candidates.append(r)

    for ratio in candidates:
        left, right = split_polygon(polygon, axis, ratio)
        if left is None or right is None:
            continue
        if _aspect_ratio(left) <= MAX_ASPECT_RATIO and _aspect_ratio(right) <= MAX_ASPECT_RATIO:
            return ratio

    # Fallback: midpoint
    return 0.5


# ─────────────────────────────────────────────
# ZONE PARTITIONING (STEP 1 OF BSP)
# ─────────────────────────────────────────────

def _compute_zone_target_areas(
    plot_area: float, rooms_by_zone: Dict[str, List[RoomSpec]]
) -> Dict[str, float]:
    """
    Compute target area for each zone proportional to the total minimum
    room area requirement for that zone (overrides static ratio).
    """
    zone_required: Dict[str, float] = {}
    total_required = 0.0

    for zone, specs in rooms_by_zone.items():
        zone_required[zone] = sum(s.min_area_sqm for s in specs)
        total_required += zone_required[zone]

    if total_required <= 0:
        return {z: plot_area * ZONE_RATIOS.get(z, 0.1) for z in rooms_by_zone}

    # Scale so proportions sum to available plot area, capped at 95%
    scale = min(1.0, (plot_area * 0.95) / total_required)
    return {zone: req * scale for zone, req in zone_required.items()}


def zone_partition(
    polygon: Polygon, rooms_by_zone: Dict[str, List[RoomSpec]]
) -> Dict[str, Polygon]:
    """
    Slice the full plot polygon into macro zones using BSP.

    Strategy:
      - Sort zones by ZONE_ORDER
      - For each zone (except last), compute how much area fraction it needs
      - Split at that fraction along the longest axis
      - Assign left/bottom piece to zone, continue with remainder
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

        # What fraction of the remaining area should this zone take?
        remaining_zones = active_zones[i:]
        remaining_target = sum(target_areas.get(z, 0) for z in remaining_zones)
        if remaining_target <= 0:
            fraction = 1.0 / len(remaining_zones)
        else:
            fraction = target_areas.get(zone, 0) / remaining_target
        fraction = max(MIN_SPLIT_RATIO, min(MAX_SPLIT_RATIO, fraction))

        axis = compute_longest_axis(remainder)
        best_ratio = _find_best_ratio(remainder, axis, fraction)
        left, right = split_polygon(remainder, axis, best_ratio)

        if left is None or right is None:
            # Cannot split — assign remainder to this and all subsequent zones
            logger.warning("Zone split failed for '%s'; assigning remainder to it.", zone)
            zone_polygons[zone] = remainder
            break

        zone_polygons[zone] = left
        remainder = right

    # Last zone gets whatever remains
    if active_zones and remainder is not None and not remainder.is_empty:
        last_zone = active_zones[-1]
        if last_zone not in zone_polygons:
            zone_polygons[last_zone] = remainder

    return zone_polygons


# ─────────────────────────────────────────────
# RECURSIVE BSP (STEP 2: WITHIN EACH ZONE)
# ─────────────────────────────────────────────

def recursive_bsp(
    polygon: Polygon,
    rooms: List[RoomSpec],
    depth: int = 0,
) -> BSPNode:
    """
    Recursively partition `polygon` to host exactly the given `rooms`.

    Base cases:
      - depth ≥ MAX_BSP_DEPTH              → assign all rooms to leaf
      - len(rooms) == 1                    → leaf node, assign room
      - len(rooms) == 0                    → dead leaf
      - polygon too small for any room     → dead leaf

    Recursive step:
      - Sort rooms by priority then min_area descending
      - Compute split ratio = area(rooms[:half]) / polygon.area
      - Split polygon along longest axis
      - Recurse into each half
    """
    node = BSPNode(polygon=polygon, depth=depth)

    if not rooms:
        return node  # dead leaf — no room to place

    if len(rooms) == 1 or depth >= MAX_BSP_DEPTH:
        # Assign the largest-priority room to this leaf
        rooms_sorted = sorted(rooms, key=lambda r: (r.priority, -r.min_area_sqm))
        node.room = rooms_sorted[0]
        return node

    # Validate polygon can host at least one room
    if polygon.area < rooms[0].min_area_sqm * 0.5:
        logger.debug("Polygon too small (%.2f sqm) to host rooms; marking dead.", polygon.area)
        return node  # dead leaf

    # Sort rooms: high-priority / large rooms first
    sorted_rooms = sorted(rooms, key=lambda r: (r.priority, -r.min_area_sqm))

    # Split rooms into two groups
    split_idx = max(1, len(sorted_rooms) // 2)
    left_rooms = sorted_rooms[:split_idx]
    right_rooms = sorted_rooms[split_idx:]

    # Determine split ratio from total area requirements
    left_area_needed = sum(r.min_area_sqm for r in left_rooms)
    right_area_needed = sum(r.min_area_sqm for r in right_rooms)
    total_needed = left_area_needed + right_area_needed

    if total_needed > 0:
        target_ratio = left_area_needed / total_needed
    else:
        target_ratio = 0.5

    target_ratio = max(MIN_SPLIT_RATIO, min(MAX_SPLIT_RATIO, target_ratio))
    axis = compute_longest_axis(polygon)
    best_ratio = _find_best_ratio(polygon, axis, target_ratio)
    left_poly, right_poly = split_polygon(polygon, axis, best_ratio)

    if left_poly is None or right_poly is None:
        # Split failed — assign all to a leaf
        node.room = sorted_rooms[0]
        return node

    # Validate that each child can host its rooms
    if left_poly.area < sum(r.min_area_sqm for r in left_rooms) * 0.4:
        logger.debug("Left polygon undersized — merging rooms onto leaf.")
        node.room = sorted_rooms[0]
        return node

    node.left = recursive_bsp(left_poly, left_rooms, depth + 1)
    node.right = recursive_bsp(right_poly, right_rooms, depth + 1)
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
      - Acute triangle (max angle > 120°)      → storage
      - Narrow strip (aspect ratio > 5:1)      → passage
      - Area > 6 sqm AND aspect < 3:1          → utility
      - Else                                   → unusable
    """
    coords = list(poly.exterior.coords)
    n = len(coords) - 1  # last == first

    aspect = _aspect_ratio(poly)
    area = poly.area

    # Check if triangle-ish (3–4 vertices)
    if n <= 4:
        # Compute interior angles using vectors
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

    if aspect > 5.0:
        return "passage"

    if area >= 6.0 and aspect <= 3.0:
        return "utility"

    return "unusable"


def handle_dead_spaces(
    leftover_polygons: List[Polygon],
) -> List[dict]:
    """
    Classify and format dead/leftover polygon fragments.
    """
    results = []
    for poly in leftover_polygons:
        if poly.area < 0.5:  # Ignore noise < 0.5 sqm
            continue
        classification = classify_dead_space(poly)
        coords = [{"x": round(x, 4), "y": round(y, 4)} for x, y in poly.exterior.coords[:-1]]
        results.append(
            {
                "polygon": coords,
                "area_sqft": round(poly.area / SQ_FT_TO_SQ_M, 2),
                "classification": classification,
            }
        )
    return results


# ─────────────────────────────────────────────
# TOP-LEVEL ORCHESTRATOR
# ─────────────────────────────────────────────

def generate_layout(
    plot_points: List[Tuple[float, float]],
    room_requirements: List[dict],
    setback: float,
    preferences: dict,
) -> dict:
    """
    Full BSP layout generation pipeline.

    Args:
        plot_points: list of (x, y) tuples in meters (exterior ring)
        room_requirements: list of dicts with 'id', 'type', 'min_area_sqm', 'priority'
        setback: setback distance in meters
        preferences: dict with boolean flags (parking, ventilation_priority, etc.)

    Returns:
        dict with:
            zone_polygons  — {zone: Polygon}
            room_leaves    — {room_id: BSPNode}
            dead_polygons  — List[Polygon]
            plot_polygon   — Polygon (original)
            inner_polygon  — Polygon (after setback)
    """
    # ── 1. Build and validate plot polygon ──────────────────────────────────
    plot_polygon = Polygon(plot_points)
    if not plot_polygon.is_valid:
        plot_polygon = make_valid(plot_polygon)
    plot_polygon = _ensure_valid(plot_polygon)

    # ── 2. Apply setback ────────────────────────────────────────────────────
    inner_polygon = apply_setback(plot_polygon, setback)

    # ── 3. Build RoomSpec list ───────────────────────────────────────────────
    specs: List[RoomSpec] = []
    for r in room_requirements:
        zone = ZONE_MAP.get(r["type"].lower(), "service")
        specs.append(
            RoomSpec(
                id=r["id"],
                type=r["type"],
                zone=zone,
                min_area_sqm=r["min_area_sqm"],
                priority=r.get("priority", 50),
            )
        )

    # Add parking zone if requested
    if preferences.get("parking"):
        specs.append(
            RoomSpec(
                id="parking_0",
                type="parking",
                zone="parking",
                min_area_sqm=15.0,
                priority=10,
            )
        )

    # ── 4. Group rooms by zone ────────────────────────────────────────────────
    rooms_by_zone: Dict[str, List[RoomSpec]] = {}
    for s in specs:
        rooms_by_zone.setdefault(s.zone, []).append(s)

    # ── 5. Macro zone partition ──────────────────────────────────────────────
    zone_polygons = zone_partition(inner_polygon, rooms_by_zone)

    # ── 6. Recursive BSP within each zone ────────────────────────────────────
    room_leaves: Dict[str, BSPNode] = {}
    zone_used_polygons: List[Polygon] = []

    for zone, zone_poly in zone_polygons.items():
        zone_rooms = rooms_by_zone.get(zone, [])
        if not zone_rooms:
            continue
        root = recursive_bsp(zone_poly, zone_rooms, depth=0)
        leaves = collect_leaves(root)
        for leaf in leaves:
            if leaf.room is not None:
                room_leaves[leaf.room.id] = leaf
                zone_used_polygons.append(leaf.polygon)

    # ── 7. Detect dead spaces ────────────────────────────────────────────────
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

    return {
        "zone_polygons": zone_polygons,
        "room_leaves": room_leaves,
        "dead_polygons": dead_polygons,
        "plot_polygon": plot_polygon,
        "inner_polygon": inner_polygon,
        "specs": specs,
    }
