"""
Verification test specifically checking rectangle layout interior walls topology.
"""
import json
import math
from pathlib import Path
from shapely.geometry import LineString
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_rectangle_wall_topology():
    samples_path = Path(__file__).resolve().parent.parent / "samples" / "rectangle.json"
    with open(samples_path) as f:
        payload = json.load(f)

    resp = client.post("/api/v1/layouts/generate", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    candidate = data["candidates"][0]
    rooms = candidate["rooms"]
    walls = candidate["walls"]
    doors = candidate["doors"]
    windows = candidate["windows"]
    val = candidate["validation"]

    assert len(rooms) > 0
    assert len(walls) > 0
    assert len(doors) > 0
    assert len(windows) > 0
    assert val["valid"] is True

    interior_walls = [w for w in walls if w["type"] == "interior"]
    exterior_walls = [w for w in walls if w["type"] == "exterior"]

    assert len(interior_walls) > 0
    assert len(exterior_walls) > 0

    # 1. All wall lengths must match distance between endpoints
    for w in walls:
        dx = w["end"]["x"] - w["start"]["x"]
        dy = w["end"]["y"] - w["start"]["y"]
        calc_len = math.hypot(dx, dy)
        assert abs(w["length"] - calc_len) < 1e-3, (
            f"Wall {w['id']} length mismatch: reported={w['length']}, calculated={calc_len}"
        )

    # 2. No two interior walls may overlap with 1D length > 1e-4
    for i in range(len(interior_walls)):
        w_i = interior_walls[i]
        line_a = LineString([(w_i["start"]["x"], w_i["start"]["y"]), (w_i["end"]["x"], w_i["end"]["y"])])
        for j in range(i + 1, len(interior_walls)):
            w_j = interior_walls[j]
            line_b = LineString([(w_j["start"]["x"], w_j["start"]["y"]), (w_j["end"]["x"], w_j["end"]["y"])])
            inters = line_a.intersection(line_b)
            if isinstance(inters, LineString):
                assert inters.length < 1e-4, (
                    f"Interior walls {w_i['id']} ({w_i['room_a']}↔{w_i['room_b']}) and "
                    f"{w_j['id']} ({w_j['room_a']}↔{w_j['room_b']}) overlap by {inters.length}m"
                )

    # 3. No duplicate room pairs for contiguous walls
    pair_counts = {}
    for w in interior_walls:
        pair = tuple(sorted([w["room_a"], w["room_b"]]))
        pair_counts[pair] = pair_counts.get(pair, 0) + 1

    for pair, count in pair_counts.items():
        assert count == 1, f"Room pair {pair} has {count} duplicate interior walls"
