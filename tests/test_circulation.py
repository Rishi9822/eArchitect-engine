"""
Tests for circulation analysis.
"""
import pytest
from shapely.geometry import Polygon
from app.layout.circulation import build_adjacency_graph, analyze_circulation


class TestAdjacencyGraph:
    def test_adjacent_rooms_connected(self):
        polys = {
            "a": Polygon([(0, 0), (5, 0), (5, 5), (0, 5)]),
            "b": Polygon([(5, 0), (10, 0), (10, 5), (5, 5)]),
        }
        graph = build_adjacency_graph(polys, [], None)
        assert "b" in graph.get("a", set())
        assert "a" in graph.get("b", set())

    def test_non_adjacent_rooms_not_connected(self):
        polys = {
            "a": Polygon([(0, 0), (4, 0), (4, 4), (0, 4)]),
            "b": Polygon([(10, 10), (14, 10), (14, 14), (10, 14)]),
        }
        graph = build_adjacency_graph(polys, [], None)
        assert "b" not in graph.get("a", set())

    def test_doors_add_connections(self):
        polys = {
            "a": Polygon([(0, 0), (4, 0), (4, 4), (0, 4)]),
            "b": Polygon([(10, 10), (14, 10), (14, 14), (10, 14)]),
        }
        doors = [{"from_room": "a", "to_room": "b"}]
        graph = build_adjacency_graph(polys, doors, None)
        assert "b" in graph.get("a", set())

    def test_entrance_creates_virtual_node(self):
        polys = {"living_0": Polygon([(0, 0), (5, 0), (5, 5), (0, 5)])}
        entrance = {"room_id": "living_0"}
        graph = build_adjacency_graph(polys, [], entrance)
        assert "ENTRANCE" in graph
        assert "living_0" in graph["ENTRANCE"]


class TestCirculationAnalysis:
    def test_fully_connected(self):
        graph = {
            "a": {"b", "c"},
            "b": {"a", "c"},
            "c": {"a", "b"},
        }
        result = analyze_circulation(graph, ["a", "b", "c"])
        assert result["connected"] is True
        assert result["reachable_rooms"] == 3

    def test_disconnected_room(self):
        graph = {
            "a": {"b"},
            "b": {"a"},
            "c": set(),  # isolated
        }
        result = analyze_circulation(graph, ["a", "b", "c"])
        assert result["connected"] is False
        assert result["reachable_rooms"] == 2

    def test_dead_end_count(self):
        graph = {
            "a": {"b"},
            "b": {"a", "c"},
            "c": {"b"},
        }
        result = analyze_circulation(graph, ["a", "b", "c"])
        # a and c each have only 1 real connection
        assert result["dead_ends"] >= 2

    def test_empty_layout(self):
        result = analyze_circulation({}, [])
        assert result["connected"] is True
        assert result["score"] == 1.0
