"""
Layout package — BSP generation, architectural elements, and circulation.
"""
from .bsp import (
    RoomSpec,
    BSPNode,
    build_room_specs,
    generate_bsp_layout,
    collect_leaves,
    classify_dead_space,
)
from .room_assignment import validate_room_assignment, AssignmentValidation
from .constraints import check_feasibility, FeasibilityResult
from .entrance import generate_entrance
from .doors import generate_doors
from .windows import generate_windows
from .parking import generate_parking_entities
from .circulation import build_adjacency_graph, analyze_circulation
