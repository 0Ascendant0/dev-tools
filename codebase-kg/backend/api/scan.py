"""Scan API endpoint for project directory scanning and analysis."""

import os
import logging
import time
from typing import Dict, Any, Optional, List, Set

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse

from database import ProjectDB
from parsers.python_parser import PythonAnalyzer
from parsers.javascript_parser import JavaScriptAnalyzer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["projects"])

# Supported file extensions
SUPPORTED_EXTENSIONS = {".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}

# Default exclusions
DEFAULT_EXCLUSIONS = {
    "node_modules", ".git", ".venv", "venv", "__pycache__",
    "dist", "build", "coverage", ".next", ".tox", "site-packages",
}

# Extensions tried when resolving an extension-less local import
JS_EXTENSIONS = [".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"]


def should_exclude(path: str, exclusions: Set[str]) -> bool:
    """Check if a path should be excluded from scanning."""
    for part in os.path.normpath(path).split(os.sep):
        if part in exclusions:
            return True
    return False


def get_relative_path(file_path: str, project_root: str) -> str:
    """Get a project-relative path with forward slashes for stable keys."""
    try:
        return os.path.relpath(file_path, project_root).replace(os.sep, "/")
    except ValueError:
        return file_path.replace(os.sep, "/")


def discover_source_files(project_path: str) -> List[str]:
    """Recursively discover analyzable source files, honouring exclusions."""
    files: List[str] = []
    for root, dirs, filenames in os.walk(project_path):
        dirs[:] = [
            d for d in dirs
            if not should_exclude(os.path.join(root, d), DEFAULT_EXCLUSIONS)
        ]
        for filename in filenames:
            if os.path.splitext(filename)[1].lower() in SUPPORTED_EXTENSIONS:
                files.append(os.path.join(root, filename))
    return sorted(files)


def _candidate_targets(project_path: str, importer_rel: str, module: str) -> List[str]:
    """Build candidate project-relative paths for a local import."""
    module = module.strip()
    if not module:
        return []

    candidates: List[str] = []
    importer_dir = os.path.dirname(importer_rel)

    if module.startswith("."):
        # Relative JS import: resolve against the importing file's directory.
        base = os.path.normpath(os.path.join(importer_dir, module))
        candidates.append(base)
        for ext in JS_EXTENSIONS:
            candidates.append(base + ext)
        for ext in JS_EXTENSIONS:
            candidates.append(os.path.join(base, "index" + ext))
    else:
        # Absolute-style import: python dotted module or a project-root relative path.
        dotted = module.replace(".", "/")
        for base in (dotted, module):
            candidates.append(base)
            candidates.append(base + ".py")
            for ext in JS_EXTENSIONS:
                candidates.append(base + ext)
            for ext in JS_EXTENSIONS:
                candidates.append(os.path.join(base, "index" + ext))

    normalised: List[str] = []
    for candidate in candidates:
        normalised.append(os.path.normpath(candidate).replace(os.sep, "/"))
    return normalised


def resolve_local_import(
    project_path: str,
    importer_rel: str,
    module: str,
    known_files: Set[str],
) -> Optional[str]:
    """Return the project-relative path a local import points at, if any."""
    for candidate in _candidate_targets(project_path, importer_rel, module):
        if candidate.startswith("../") or candidate == "..":
            continue
        if candidate in known_files:
            return candidate
    return None


@router.post("/scan")
async def scan_project(
    background_tasks: BackgroundTasks,
    project_name: str,
    project_path: str,
):
    """Initiate project scanning in the background."""
    if not project_path or not os.path.isdir(project_path):
        raise HTTPException(status_code=400, detail="Project path does not exist or is not a directory")

    project_path = os.path.abspath(project_path)
    db = ProjectDB()

    existing = db.get_project_by_path(project_path)
    if existing:
        return JSONResponse(
            status_code=200,
            content={"message": "Project already scanned", "project_id": existing["id"]},
        )

    project = db.create_project(project_name or os.path.basename(project_path), project_path)
    if not project:
        raise HTTPException(status_code=500, detail="Failed to create project entry")

    background_tasks.add_task(do_scan_project, project_path, project["id"])

    return JSONResponse(
        status_code=202,
        content={"message": "Scan started", "project_id": project["id"]},
    )


import hashlib
from ir_schema import get_registry, parse_file, list_languages

def _file_hash(path: str) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return ""

def do_scan_project(project_path: str, project_id: int):
    """Analyse project files, using incremental re-analysis when files unchanged.
    
    Only re-analyze files whose hash has changed since last scan.
    This supports the incremental analysis requirement without
    reprocessing the entire project.
    """
    logger.info("Starting scan of project: %s (ID: %s)", project_path, project_id)
    started = time.time()
    db = ProjectDB()

    scan = db.create_scan_history(project_id, scan_type="full", status="in_progress")
    scan_id = scan["id"] if scan else None

    try:
        from ir_schema import get_registry as get_parser_registry
        parser_reg = get_parser_registry()

        source_files = discover_source_files(project_path)
        logger.info("Discovered %d source files", len(source_files))

        # Pass 1: register every file so import targets can be resolved.
        # Use incremental analysis: check file hash to skip unchanged files.
        file_records: Dict[str, Dict] = {}
        files_to_analyse: List[str] = []  # files that need re-analysis
        files_cached: int = 0

        for file_path in source_files:
            rel_path = get_relative_path(file_path, project_path)
            current_hash = _file_hash(file_path)
            source_record = db.get_source_file(project_id, rel_path)

            # Incremental: if file hash matches last scan, reuse previous results
            if source_record and source_record.get("file_hash") == current_hash:
                # Use cached results - copy previous import/function/class data
                # For now, mark as cached and skip re-analysis
                files_cached += 1
                file_records[rel_path] = source_record
                continue

            files_to_analyse.append(file_path)
            file_records[rel_path] = db.create_source_file(
                project_id=project_id,
                name=os.path.basename(rel_path),
                relative_path=rel_path,
                absolute_path=file_path,
                file_extension=os.path.splitext(file_path)[1].lower(),
                file_size=os.path.getsize(file_path) if os.path.exists(file_path) else 0,
                file_hash=current_hash,
            )

        known_files = {rel for rel in file_records if file_records[rel]}

        logger.info("%d files cached (unchanged), %d files to analyse", files_cached, len(files_to_analyse))

        # Pass 2: analyse only files that changed or are new
        dependency_count = 0
        function_count = 0
        class_count = 0

        # Track which files were re-analysed for dependency resolution
        re_analysed_files: Set[str] = set()

        for file_path in files_to_analyse:
            rel_path = get_relative_path(file_path, project_path)
            source_record = file_records.get(rel_path)
            if not source_record:
                continue

            file_ext = os.path.splitext(file_path)[1].lower()
            if file_ext == ".py":
                result = python_analyzer.analyze_file(file_path)
            elif file_ext in {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}:
                result = js_analyzer.analyze_file(file_path)
            else:
                continue

            re_analysed_files.add(rel_path)

            for imp in result.get("imports", []):
                module_name = imp.get("module") or ""
                if not module_name:
                    continue

                target_rel = (
                    resolve_local_import(project_path, rel_path, module_name, known_files)
                    if imp.get("is_local")
                    else None
                )

                if target_rel:
                    target_record = file_records.get(target_rel)
                    if target_record:
                        db.create_import_dependency(
                            project_id=project_id,
                            source_file_id=source_record["id"],
                            target_file_id=target_record["id"],
                            import_type="internal",
                            import_statement=module_name,
                            resolved=True,
                        )
                        dependency_count += 1
                else:
                    db.create_import_dependency(
                        project_id=project_id,
                        source_file_id=source_record["id"],
                        target_file_id=0,
                        import_type="unresolved" if imp.get("is_local") else "external",
                        import_statement=module_name,
                        resolved=False,
                    )

            for func in result.get("functions", []):
                db.create_function_definition(
                    project_id=project_id,
                    source_file_id=source_record["id"],
                    name=func.get("name", ""),
                    line_number=func.get("line", 0) or 0,
                )
                function_count += 1

            for cls in result.get("classes", []):
                db.create_class_definition(
                    project_id=project_id,
                    source_file_id=source_record["id"],
                    name=cls.get("name", ""),
                    line_number=cls.get("line", 0) or 0,
                )
                class_count += 1

        # Update scan history with real counts
        actual_analysed = len(files_to_analyse) + files_cached
        if scan_id is not None:
            db.update_scan_history(
                scan_id=scan_id,
                status="completed",
                duration_seconds=round(time.time() - started, 3),
                files_analyzed=actual_analysed,
                dependencies_found=dependency_count,
            )

        logger.info(
            "Scan completed for project %s: %d total files, %d cached, %d re-analysed, %d internal dependencies, %d functions, %d classes",
            project_id, actual_analysed, files_cached, len(files_to_analyse),
            dependency_count, function_count, class_count,
        )

    except Exception as exc:  # noqa: BLE001 - background task must not crash the server
        logger.exception("Scan failed for project ID %s: %s", project_id, exc)
        db.set_project_status(project_id, "failed")
        if scan_id is not None:
            db.update_scan_history(scan_id=scan_id, status="failed")