"""Graph API endpoint for dependency graph retrieval."""

from fastapi import APIRouter, HTTPException
from database import ProjectDB
from graph.graph_builder import DependencyGraph

router = APIRouter(prefix="/api/projects", tags=["projects"])
db = ProjectDB()


@router.get("/{project_id}/graph")
async def get_graph(project_id: int):
    """Retrieve graph nodes and edges."""
    # Get project info
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get source files
    source_files = db.get_source_files_by_project(project_id)
    if not source_files:
        raise HTTPException(status_code=404, detail="No source files found for project")

    # Get import dependencies
    import_dependencies = db.get_all_imports(project_id)

    # Build graph
    graph_builder = DependencyGraph()
    graph = graph_builder.build_graph(source_files, import_dependencies)

    return {
        "nodes": graph_builder.get_nodes(),
        "edges": graph_builder.get_edges(),
        "statistics": {
            "node_count": graph.number_of_nodes(),
            "edge_count": graph.number_of_edges(),
        },
    }


@router.get("/{project_id}/cycles")
async def get_cycles(project_id: int):
    """Detect import cycles in the project's dependency graph."""
    if not db.get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    source_files = db.get_source_files_by_project(project_id)
    import_dependencies = db.get_all_imports(project_id)

    graph_builder = DependencyGraph()
    graph_builder.build_graph(source_files, import_dependencies)

    by_id = {f["id"]: f["relative_path"] for f in source_files}
    cycles = [
        [by_id.get(node_id, str(node_id)) for node_id in cycle]
        for cycle in graph_builder.find_cycles()
    ]
    return {"cycles": cycles, "count": len(cycles)}