"""Tests for the NetworkX dependency graph builder."""

from graph.graph_builder import DependencyGraph


FILES = [
    {"id": 1, "name": "a.py", "relative_path": "a.py", "file_extension": ".py"},
    {"id": 2, "name": "b.py", "relative_path": "b.py", "file_extension": ".py"},
    {"id": 3, "name": "app.js", "relative_path": "app.js", "file_extension": ".js"},
]

DEPS = [
    {"source_file_id": 1, "target_file_id": 2, "import_type": "internal", "resolved": True},
    {"source_file_id": 3, "target_file_id": 2, "import_type": "internal", "resolved": True},
    {"source_file_id": 1, "target_file_id": 0, "import_type": "external", "resolved": False},
]


def build():
    builder = DependencyGraph()
    graph = builder.build_graph(FILES, DEPS)
    return builder, graph


def test_nodes_and_internal_edges_only():
    builder, graph = build()

    assert graph.number_of_nodes() == 3
    # Only internal dependencies become edges
    assert graph.number_of_edges() == 2
    assert len(builder.get_nodes()) == 3
    assert len(builder.get_edges()) == 2


def test_node_metadata_and_colours():
    builder, _ = build()
    nodes = {node["id"]: node for node in builder.get_nodes()}

    assert nodes[1]["label"] == "a.py"
    assert nodes[1]["extension"] == ".py"
    assert nodes[1]["color"] != nodes[3]["color"]


def test_degree_and_neighbours():
    builder, _ = build()

    assert builder.get_node_degree(2) == {"in": 2, "out": 0}
    assert builder.get_node_degree(1) == {"in": 0, "out": 1}
    assert builder.get_neighbors(1, "out") == [2]
    assert set(builder.get_neighbors(2, "in")) == {1, 3}


def test_shortest_path_and_components():
    builder, _ = build()

    assert builder.find_shortest_path(1, 2) == [1, 2]
    assert builder.find_shortest_path(2, 1) is None
    assert len(builder.find_connected_components()) == 1


def test_cycle_detection():
    builder = DependencyGraph()
    builder.build_graph(
        FILES[:2],
        [
            {"source_file_id": 1, "target_file_id": 2, "import_type": "internal"},
            {"source_file_id": 2, "target_file_id": 1, "import_type": "internal"},
        ],
    )

    cycles = builder.find_cycles()
    assert len(cycles) == 1
    assert set(cycles[0]) == {1, 2}
