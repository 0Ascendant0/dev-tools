"""Project management API endpoints."""

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException

from database import ProjectDB

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["projects"])

# Dependency - in a real app, this would be injected per-request
db = ProjectDB()


@router.get("")
async def list_projects():
    """Retrieve previously analysed projects."""
    projects = db.get_all_projects()
    return {"projects": projects, "count": len(projects)}


@router.get("/{project_id}")
async def get_project(project_id: int):
    """Retrieve project information."""
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get source files
    files = db.get_source_files_by_project(project_id)

    return {
        "project": project,
        "files": files,
        "file_count": len(files),
    }


@router.get("/{project_id}/files")
async def get_files(project_id: int):
    """Retrieve discovered source files."""
    if not db.get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    source_files = db.get_source_files_by_project(project_id)
    return {"files": source_files, "count": len(source_files)}


@router.get("/{project_id}/files/{file_id}")
async def get_file_details(project_id: int, file_id: int):
    """Retrieve file analysis details."""
    if not db.get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    source_files = db.get_source_files_by_project(project_id)
    source_file = next((f for f in source_files if f["id"] == file_id), None)
    if not source_file:
        raise HTTPException(status_code=404, detail="File not found")

    imports = db.get_imports_from_file(project_id, source_file["id"])
    functions = db.get_functions_by_file(project_id, source_file["id"])
    classes = db.get_classes_by_file(project_id, source_file["id"])
    imports_to = db.get_imports_to_file(project_id, source_file["id"])

    # Resolve file ids to readable paths for the client
    by_id = {f["id"]: f for f in source_files}
    for dep in imports + imports_to:
        target = by_id.get(dep.get("target_file_id"))
        dep["target_path"] = target["relative_path"] if target else None
        source = by_id.get(dep.get("source_file_id"))
        dep["source_path"] = source["relative_path"] if source else None

    return {
        "file": source_file,
        "imports": imports,
        "functions": functions,
        "classes": classes,
        "imports_to": imports_to,
        "import_count": len(imports),
        "dependents_count": len(imports_to),
    }


@router.delete("/{project_id}")
async def delete_project(project_id: int):
    """Remove a project and all of its analysis data."""
    if not db.get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    db.delete_project(project_id)
    return {"message": "Project deleted", "project_id": project_id}


@router.post("/{project_id}/refresh")
async def refresh_project(project_id: int, background_tasks: BackgroundTasks):
    """Re-run the analysis for an existing project."""
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    from api.scan import do_scan_project

    db.set_project_status(project_id, "scanning")
    background_tasks.add_task(do_scan_project, project["root_path"], project_id)

    return {"message": "Refresh started", "project_id": project_id}