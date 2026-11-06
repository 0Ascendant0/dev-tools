"""Extension management API endpoints.

Handles listing, installing, uninstalling, enabling, disabling, and updating
extensions. Also provides language capability information.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse

from extensions.manifest import (
    get_extension_registry,
    install_extension,
    enable_extension,
    disable_extension,
    is_extension_enabled,
    list_extensions,
    ExtensionManifest,
    register_extension,
    unregister_extension,
)
from ir_schema import get_registry, list_languages, get_capability

router = APIRouter(prefix="/api/extensions", tags=["extensions"])


@router.get("/languages")
async def list_supported_languages():
    """List all supported languages with their capabilities."""
    registry = get_registry()
    langs = list_languages()
    capabilities = {name: get_capability(name) for name in langs}
    return {"languages": langs, "capabilities": capabilities}


@router.get("/extensions")
async def list_extensions_endpoint(category: Optional[str] = None):
    """List all extensions, optionally filtered by category."""
    reg = get_extension_registry()
    exts = reg.list_extensions(category)
    return {"extensions": [ext.__dict__ for ext in exts]}


@router.get("/extensions/{extension_id}")
async def get_extension(extension_id: str):
    """Get details for a specific extension."""
    reg = get_extension_registry()
    ext = reg.get_extension(extension_id)
    if ext is None:
        raise HTTPException(status_code=404, detail="Extension not found")
    return {"extension": ext.__dict__}


@router.post("/extensions/{extension_id}/install")
async def install_extension_endpoint(
    extension_id: str,
    background_tasks: BackgroundTasks,
):
    """Install an extension by ID.

    Checks dependencies, resolves compatibility, and installs the extension.
    """
    reg = get_extension_registry()

    # Load the manifest - in a real app this would download from a registry
    # For now, we look for it locally
    from extensions.manifest import load_manifest

    manifest = load_manifest(extension_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="Extension manifest not found")

    # Get all currently registered extensions
    all_exts = {}
    for eid, ext in reg._extensions.items():
        all_exts[eid] = ext
    # Also include built-in language extensions
    for lang in ["python", "javascript", "typescript", "java", "c", "cpp", "csharp", "php", "dart"]:
        if lang in reg._extensions:
            all_exts[lang] = reg._extensions[lang]

    # Attempt installation
    result = install_extension(manifest, all_exts)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["reason"])

    # Add to background tasks for actual install processing
    background_tasks.add_task(_install_extension_background, manifest, all_exts)

    return {"message": "Installation started", "extension_id": extension_id}


async def _install_extension_background(manifest: ExtensionManifest, all_exts: dict):
    """Background task to install an extension."""
    # In a real app: extract package, verify integrity, load module
    # For now, just save the manifest
    from extensions.manifest import save_manifest

    save_manifest(manifest)


@router.post("/extensions/{extension_id}/uninstall")
async def uninstall_extension_endpoint(extension_id: str):
    """Uninstall an extension by ID."""
    reg = get_extension_registry()
    from extensions.manifest import delete_manifest

    success = reg.unregister_extension(extension_id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot uninstall built-in language")

    # Also delete from filesystem
    delete_manifest(extension_id)

    return {"message": f"Extension {extension_id} uninstalled"}


@router.post("/extensions/{extension_id}/enable")
async def enable_extension_endpoint(extension_id: str):
    """Enable an extension."""
    reg = get_extension_registry()
    success = enable_extension(extension_id)
    if not success:
        raise HTTPException(status_code=404, detail="Extension not found")
    return {"message": f"Extension {extension_id} enabled"}


@router.post("/extensions/{extension_id}/disable")
async def disable_extension_endpoint(extension_id: str):
    """Disable an extension."""
    reg = get_extension_registry()
    success = disable_extension(extension_id)
    if not success:
        raise HTTPException(status_code=404, detail="Extension not found")
    return {"message": f"Extension {extension_id} disabled"}


@router.get("/extensions/{extension_id}/enabled")
async def is_extension_enabled_endpoint(extension_id: str):
    """Check if an extension is enabled."""
    reg = get_extension_registry()
    enabled = is_extension_enabled(extension_id)
    return {"extension_id": extension_id, "enabled": enabled}


@router.get("/extensions/{extension_id}/dependencies")
async def extension_dependencies(extension_id: str):
    """Check dependency status for an extension."""
    reg = get_extension_registry()
    from extensions.manifest import get_extension_registry as get_reg

    all_exts = {}
    for eid, ext in reg._extensions.items():
        all_exts[eid] = ext
    for lang in ["python", "javascript", "typescript", "java", "c", "cpp", "csharp", "php", "dart"]:
        if lang in reg._extensions:
            all_exts[lang] = reg._extensions[lang]

    manifest = reg._extensions.get(extension_id)
    if not manifest:
        raise HTTPException(status_code=404, detail="Extension not found")

    deps = reg.check_dependency(extension_id, all_exts)
    return {"extension_id": extension_id, "dependencies": deps}