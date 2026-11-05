"""Search API endpoint for files, functions, and classes."""

import logging
import sqlite3

from fastapi import APIRouter, HTTPException
from database import ProjectDB

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["projects"])
db = ProjectDB()


@router.get("/{project_id}/search")
async def search_project(
    project_id: int,
    query: str,
):
    """Search for files, functions, and classes in a project."""
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Search in source file names and paths
    source_files = db.get_source_files_by_project(project_id)

    results = {
        "files": [],
        "functions": [],
        "classes": [],
    }

    by_id = {f["id"]: f for f in source_files}

    # Search file names and paths
    query_lower = query.lower()
    for f in source_files:
        name = f.get("name", "").lower()
        rel_path = f.get("relative_path", "").lower()
        if query_lower in name or query_lower in rel_path:
            results["files"].append({
                "id": f["id"],
                "name": f.get("name", ""),
                "path": f.get("relative_path", ""),
                "extension": f.get("file_extension", ""),
            })

    # Search would ideally also look in parsed function/class definitions
    # For now, we'll also check the database tables if they exist
    try:
        # Search function definitions
        # This is a simplified query; in production we'd use full-text search
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row

        # Search functions
        func_rows = conn.execute(
            "SELECT * FROM function_definitions WHERE project_id = ? AND name LIKE ?",
            (project_id, f"%{query}%"),
        ).fetchall()

        for row in func_rows:
            source = by_id.get(row["source_file_id"])
            results["functions"].append({
                "name": row["name"],
                "line": row["line_number"],
                "file": source["relative_path"] if source else None,
                "file_id": row["source_file_id"],
            })

        # Search classes
        cls_rows = conn.execute(
            "SELECT * FROM class_definitions WHERE project_id = ? AND name LIKE ?",
            (project_id, f"%{query}%"),
        ).fetchall()

        for row in cls_rows:
            source = by_id.get(row["source_file_id"])
            results["classes"].append({
                "name": row["name"],
                "line": row["line_number"],
                "file": source["relative_path"] if source else None,
                "file_id": row["source_file_id"],
            })

        conn.close()
    except Exception as e:
        logger.error(f"Search database error: {e}")

    return results