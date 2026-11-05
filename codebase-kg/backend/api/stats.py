"""Project statistics API endpoint."""

import logging
import sqlite3

from fastapi import APIRouter, HTTPException

from database import ProjectDB

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["stats"])
db = ProjectDB()


@router.get("/{project_id}/statistics")
async def get_project_statistics(project_id: int):
    """Retrieve comprehensive project statistics."""
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    source_files = db.get_source_files_by_project(project_id)

    if not source_files:
        return {
            "total_source_files": 0,
            "total_python_files": 0,
            "total_javascript_files": 0,
            "total_internal_dependencies": 0,
            "total_unresolved_imports": 0,
            "total_detected_functions": 0,
            "total_detected_classes": 0,
            "files_by_extension": {},
        }

    # Count files by extension
    files_by_extension = {}
    total_python = 0
    total_js_ts = 0

    for f in source_files:
        ext = f.get("file_extension", "")
        files_by_extension[ext] = files_by_extension.get(ext, 0) + 1

        if ext == ".py":
            total_python += 1
        elif ext in {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}:
            total_js_ts += 1

    # Import dependency counts
    import_deps = db.get_all_imports(project_id)
    internal = len([d for d in import_deps if d.get("import_type") == "internal"])
    unresolved = len([d for d in import_deps if d.get("import_type") == "unresolved"])

    # Function and class counts
    total_functions = 0
    total_classes = 0

    try:
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        total_functions = conn.execute(
            "SELECT COUNT(*) FROM function_definitions WHERE project_id = ?",
            (project_id,),
        ).fetchone()[0] or 0
        total_classes = conn.execute(
            "SELECT COUNT(*) FROM class_definitions WHERE project_id = ?",
            (project_id,),
        ).fetchone()[0] or 0
        conn.close()
    except Exception as exc:  # noqa: BLE001 - statistics must not 500 the dashboard
        logger.error("Statistics database error: %s", exc)

    return {
        "total_source_files": len(source_files),
        "total_python_files": total_python,
        "total_javascript_files": total_js_ts,
        "total_internal_dependencies": internal,
        "total_unresolved_imports": unresolved,
        "total_detected_functions": total_functions,
        "total_detected_classes": total_classes,
        "files_by_extension": files_by_extension,
    }