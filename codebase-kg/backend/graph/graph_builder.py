"""Dependency graph builder using NetworkX for graph processing."""

import os

import networkx as nx
from typing import Any, Dict, List, Optional, Set


class DependencyGraph:
    """Builds and manages dependency graphs using NetworkX."""

    def __init__(self):
        # Directed graph: edge from A -> B means A imports B (A depends on B)
        self.graph = nx.DiGraph()
        self.node_info: Dict[int, Dict] = {}  # node_id -> metadata
        self.adjacency_cache: Optional[Dict] = None

    def build_graph(self, source_files: List[Dict], import_dependencies: List[Dict]) -> nx.DiGraph:
        """Build a dependency graph from source files and import dependencies."""
        self.graph = nx.DiGraph()
        self.node_info = {}
        self.adjacency_cache = None

        # Add nodes for all source files
        for file_info in source_files:
            file_id = file_info.get("id", 0)
            relative_path = file_info.get("relative_path", "")
            file_extension = file_info.get("file_extension", "")
            name = file_info.get("name", os.path.basename(relative_path))

            # Determine node color/style based on file type
            node_color = self._get_node_color(file_extension)
            node_shape = self._get_node_shape(file_extension)

            self.graph.add_node(
                file_id,
                label=os.path.basename(relative_path),
                path=relative_path,
                extension=file_extension,
                color=node_color,
                shape=node_shape,
            )
            self.node_info[file_id] = {
                "relative_path": relative_path,
                "extension": file_extension,
                "name": name,
            }

        # Add edges for import dependencies
        for dep in import_dependencies:
            source_id = dep.get("source_file_id", 0)
            target_id = dep.get("target_file_id", 0)
            import_type = dep.get("import_type", "internal")

            # Only add internal dependencies as graph edges
            if import_type == "internal":
                # Check if both nodes exist
                if self.graph.has_node(source_id) and self.graph.has_node(target_id):
                    # Edge direction: source -> target means source imports target
                    # But we want to show: target depends on source (imports flow from source to target)
                    # Actually, let's make the edge mean "source imports target"
                    # So if A imports B, we add edge A -> B
                    self.graph.add_edge(
                        source_id,
                        target_id,
                        import_type=import_type,
                        resolved=dep.get("resolved", False),
                    )

        return self.graph

    def _get_node_color(self, extension: str) -> str:
        """Get color for node based on file extension."""
        colors = {
            ".py": "#ff6b6b",      # Red for Python
            ".js": "#ffd93d",      # Yellow for JavaScript
            ".jsx": "#ffd93d",     # Yellow for JSX
            ".mjs": "#ffd93d",     # Yellow for ES modules JS
            ".cjs": "#ffd93d",     # Yellow for CommonJS
            ".ts": "#ffe66d",      # Orange for TypeScript
            ".tsx": "#ffe66d",     # Orange for TSX
            ".json": "#aaaaff",    # Light blue for JSON
            ".md": "#aaffaa",      # Green for markdown
        }
        return colors.get(extension, "#787878")

    def _get_node_shape(self, extension: str) -> str:
        """Get shape for node based on file extension."""
        shapes = {
            ".py": "ellipse",
            ".js": "diamond",
            ".jsx": "diamond",
            ".mjs": "diamond",
            ".cjs": "diamond",
            ".ts": "box",
            ".tsx": "box",
            ".json": "icon",
            ".md": "folder",
        }
        return shapes.get(extension, "ellipse")

    def get_nodes(self) -> List[Dict]:
        """Get all nodes with their attributes."""
        nodes = []
        for node_id, data in self.graph.nodes(data=True):
            nodes.append({
                "id": node_id,
                "label": data.get("label", str(node_id)),
                "path": data.get("path", ""),
                "extension": data.get("extension", ""),
                "color": data.get("color", "#787878"),
                "shape": data.get("shape", "ellipse"),
            })
        return nodes

    def get_edges(self) -> List[Dict]:
        """Get all edges with their attributes."""
        edges = []
        for source_id, target_id, data in self.graph.edges(data=True):
            edges.append({
                "source": source_id,
                "target": target_id,
                "import_type": data.get("import_type", "internal"),
                "resolved": data.get("resolved", False),
            })
        return edges

    def get_neighbors(self, node_id: int, direction: str = "out") -> List[int]:
        """Get neighboring nodes (imports or dependents)."""
        if direction == "out":
            # Outgoing edges: files this node imports
            return list(self.graph.successors(node_id))
        elif direction == "in":
            # Incoming edges: files that import this node
            return list(self.graph.predecessors(node_id))
        return []

    def get_node_degree(self, node_id: int) -> Dict[str, int]:
        """Get in-degree and out-degree of a node."""
        if not self.graph.has_node(node_id):
            return {"in": 0, "out": 0}
        in_degree = self.graph.in_degree(node_id)
        out_degree = self.graph.out_degree(node_id)
        return {"in": in_degree, "out": out_degree}

    def find_connected_components(self) -> List[Set[int]]:
        """Find weakly connected components in the graph."""
        try:
            return list(nx.weakly_connected_components(self.graph))
        except nx.NetworkXError:
            return []

    def find_shortest_path(self, source: int, target: int) -> Optional[List[int]]:
        """Find shortest path between two nodes."""
        try:
            return nx.shortest_path(self.graph, source, target)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

    def find_cycles(self) -> List[List[int]]:
        """Find cycles in the directed graph."""
        try:
            return list(nx.simple_cycles(self.graph))
        except nx.NetworkXError:
            return []