"""Extension manifest format and registry for the Codebase Knowledge Graph.

Defines the versioned manifest format that extensions must adhere to,
and provides a local registry for discovered/installed extensions.
"""

from __future__ import annotations

import json
import os
import hashlib
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from ir_schema import ParserRegistry, ParserInterface, get_registry


# -- Manifest Format ---------------------------------------------------------

MANIFEST_FILENAME = "extension_manifest.json"
INSTALLED_EXTENSIONS_DIR = "installed_extensions"

# Built-in language names that should not be overwritten by extensions
BUILT_IN_LANGUAGES = frozenset({
    "python", "javascript", "typescript", "java", "c", "cpp", "c_sharp", "php", "dart"
})


@dataclass
class ExtensionManifest:
    """The manifest describing a single extension.

    All downloadable extensions must conform to this format.
    """
    id: str  # Unique identifier (UUID)
    name: str
    description: str
    version: str  # Semantic version (major.minor.patch)
    publisher: str
    category: str  # "language", "framework", "analysis", "version_control"
    supported_language: Optional[str] = None  # Language this extension targets
    supported_frameworks: Optional[List[str]] = None  # Frameworks this extends
    required_core_version: str = "0.1.0"  # Minimum core version
    required_dependencies: Optional[List[str]] = None  # Other extension IDs
    optional_dependencies: Optional[List[str]] = None  # Other extension IDs
    capabilities: List[str] = field(default_factory=list)  # What it adds
    entry_point: str = ""  # Module/path to load
    integrity_hash: str = ""  # SHA-256 of the extension package
    published_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    is_trusted: bool = False  # Whether from a trusted publisher


def manifest_id() -> str:
    """Generate a unique ID for a new extension manifest."""
    return str(uuid.uuid4())


def compute_integrity_hash(content: bytes) -> str:
    """Compute SHA-256 integrity hash for an extension package."""
    return hashlib.sha256(content).hexdigest()


def manifest_path_for(extension_id: str) -> str:
    """Get the filesystem path for an installed extension's manifest."""
    return os.path.join(INSTALLED_EXTENSIONS_DIR, extension_id, MANIFEST_FILENAME)


def load_manifest(extension_id: str) -> Optional[ExtensionManifest]:
    """Load an extension manifest from the local registry."""
    path = manifest_path_for(extension_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Convert to ExtensionManifest - handle both old and new formats
        return ExtensionManifest(**data)
    except (json.JSONDecodeError, TypeError, KeyError):
        return None


def save_manifest(manifest: ExtensionManifest) -> None:
    """Save an extension manifest to the local registry."""
    os.makedirs(INSTALLED_EXTENSIONS_DIR, exist_ok=True)
    ext_dir = os.path.join(INSTALLED_EXTENSIONS_DIR, manifest.id)
    os.makedirs(ext_dir, exist_ok=True)
    path = os.path.join(ext_dir, MANIFEST_FILENAME)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest.__dict__, f, indent=2)


def delete_manifest(extension_id: str) -> bool:
    """Delete an extension manifest from the local registry."""
    ext_dir = os.path.join(INSTALLED_EXTENSIONS_DIR, extension_id)
    if os.path.exists(ext_dir):
        import shutil
        shutil.rmtree(ext_dir)
        return True
    return False


# -- Extension Registry ------------------------------------------------------

class ExtensionRegistry:
    """Local registry for discovered and installed extensions.

    Tracks:
    - Built-in languages (no install/remove actions)
    - Downloadable extensions by category
    - Extension dependencies and compatibility
    - Enable/disable status per extension
    """

    def __init__(self):
        self._extensions: Dict[str, ExtensionManifest] = {}
        self._by_category: Dict[str, List[str]] = {}  # category -> [extension_ids]
        self._enabled: Dict[str, bool] = {}  # extension_id -> enabled status
        self._initialized = False

        # Register built-in languages immediately
        self._register_built_ins()

    def _register_built_ins(self) -> None:
        """Register the nine built-in languages as 'extensions' without install/remove."""
        from ir_schema import get_registry as get_parser_registry
        parser_reg = get_parser_registry()

        for lang_name, info in parser_reg.list_languages().items():
            manifest = ExtensionManifest(
                id=lang_name,
                name=info["name"].replace("_", " ").title(),
                description=f"Built-in {info['name']} language support",
                version="1.0.0",
                publisher="Codebase KG",
                category="language",
                supported_language=lang_name,
                capabilities=[],
            )
            self._extensions[lang_name] = manifest
            self._enabled[lang_name] = True  # Always enabled

            # Track by category
            if manifest.category not in self._by_category:
                self._by_category[manifest.category] = []
            if lang_name not in self._by_category[manifest.category]:
                self._by_category[manifest.category].append(lang_name)

    def register_extension(self, manifest: ExtensionManifest) -> None:
        """Register a downloaded/loaded extension."""
        self._extensions[manifest.id] = manifest
        self._enabled[manifest.id] = True  # Default: enabled

        if manifest.category not in self._by_category:
            self._by_category[manifest.category] = []
        if manifest.id not in self._by_category[manifest.category]:
            self._by_category[manifest.category].append(manifest.id)

    def unregister_extension(self, extension_id: str) -> bool:
        """Unregister an extension."""
        if extension_id in self._extensions:
            # Don't allow unregistering built-in languages
            if extension_id in BUILT_IN_LANGUAGES:
                return False

            del self._extensions[extension_id]
            self._enabled.pop(extension_id, None)

            # Remove from category tracking
            for cat, exts in self._by_category.items():
                if extension_id in exts:
                    exts.remove(extension_id)

            return True
        return False

    def enable_extension(self, extension_id: str) -> bool:
        """Enable an extension."""
        if extension_id in self._extensions:
            self._enabled[extension_id] = True
            return True
        return False

    def disable_extension(self, extension_id: str) -> bool:
        """Disable an extension."""
        if extension_id in self._extensions:
            self._enabled[extension_id] = False
            return True
        return False

    def is_enabled(self, extension_id: str) -> bool:
        """Check if an extension is enabled."""
        # Built-in languages are always enabled
        if extension_id in BUILT_IN_LANGUAGES:
            return True
        return self._enabled.get(extension_id, False)

    def get_extension(self, extension_id: str) -> Optional[ExtensionManifest]:
        """Get an extension manifest by ID."""
        return self._extensions.get(extension_id)

    def list_extensions(self, category: Optional[str] = None) -> List[ExtensionManifest]:
        """List all extensions, optionally filtered by category."""
        if category:
            ext_ids = self._by_category.get(category, [])
            return [self._extensions[eid] for eid in ext_ids if eid in self._extensions]
        return list(self._extensions.values())

    def list_languages(self) -> Dict[str, Dict]:
        """List all registered languages (built-in + extension-provided)."""
        result = {}
        for eid, manifest in self._extensions.items():
            if manifest.category == "language":
                result[eid] = {
                    "name": manifest.name,
                    "extensions": manifest.supported_language,
                    "capability": "full",  # Built-in parsers are full
                }
        return result

    def check_dependency(
        self, extension_id: str, all_extensions: Dict[str, ExtensionManifest]
    ) -> Dict[str, any]:
        """Check if an extension's dependencies are satisfied.

        Returns a dict with:
        - satisfied: bool
        - missing: List[str] - dependency IDs not installed
        - incompatible: List[str] - dependency IDs with version conflicts
        - circular: bool - whether circular deps were detected
        """
        manifest = self._extensions.get(extension_id)
        if not manifest:
            return {"satisfied": False, "missing": [], "incompatible": [], "circular": False}

        required = manifest.required_dependencies or []
        optional = manifest.optional_dependencies or []

        missing = []
        incompatible = []

        # Check required deps
        for dep_id in required:
            dep_manifest = all_extensions.get(dep_id)
            if not dep_manifest:
                missing.append(dep_id)
            elif not self._is_compatible(dep_id, dep_manifest, all_extensions):
                incompatible.append(dep_id)

        # Check optional deps (warn but don't block)
        # optional_missing = [d for d in optional if d not in all_extensions]

        # Check for circular deps (simple check)
        # An extension depends on another that depends on the first
        visited = set()
        circular = False

        def check_circular(eid: str, path: List[str]) -> bool:
            nonlocal circular
            if eid in path:
                circular = True
                return True
            if eid in visited:
                return False
            visited.add(eid)
            dep_manifest = all_extensions.get(eid)
            if dep_manifest and dep_manifest.required_dependencies:
                for dep in dep_manifest.required_dependencies:
                    check_circular(dep, path + [eid])
            return circular

        # Check from each required dep
        for dep_id in required:
            check_circular(dep_id, [])

        return {
            "satisfied": len(missing) == 0,
            "missing": missing,
            "incompatible": incompatible,
            "circular": circular,
        }

    def _is_compatible(
        self, dep_id: str, dep_manifest: ExtensionManifest,
        all_extensions: Dict[str, ExtensionManifest],
    ) -> bool:
        """Check if a dependency is compatible with the core and other extensions."""
        # Check required core version
        core_version = dep_manifest.required_core_version
        # Simple version string comparison - in production use proper semver
        # For now, just check it's not an obviously broken version
        if core_version and core_version > "1.0.0":
            # Placeholder: would need proper semver comparison
            pass
        return True

    def install_extension(self, manifest: ExtensionManifest, 
                          all_extensions: Dict[str, ExtensionManifest]) -> Dict[str, any]:
        """Attempt to install an extension, checking dependencies first.

        Returns a dict with:
        - success: bool
        - reason: str (if failed)
        - checked_deps: dict from check_dependency
        """
        dep_check = self.check_dependency(manifest.id, all_extensions)
        if not dep_check["satisfied"]:
            return {
                "success": False,
                "reason": f"Unsatisfied dependencies: {dep_check['missing']} + {dep_check['incompatible']}",
                "checked_deps": dep_check,
            }

        # Check for circular deps involving this extension
        # (simple check: does this extension's deps form a cycle?)
        visited = set()

        def check_circular_from(eid: str, path: List[str]) -> bool:
            if eid in path:
                return True
            if eid in visited:
                return False
            visited.add(eid)
            ex = all_extensions.get(eid)
            if ex and ex.required_dependencies:
                for dep in ex.required_dependencies:
                    if check_circular_from(dep, path + [eid]):
                        return True
            return False

        # Check from all required deps of this extension
        for dep in manifest.required_dependencies or []:
            if check_circular_from(dep, []):
                return {
                    "success": False,
                    "reason": "Circular dependency detected",
                    "checked_deps": dep_check,
                }

        # If we get here, install
        self.register_extension(manifest)
        return {
            "success": True,
            "reason": "Installed successfully",
            "checked_deps": dep_check,
        }


# Global registry instance
_registry: ExtensionRegistry = ExtensionRegistry()


def get_extension_registry() -> ExtensionRegistry:
    """Return the global extension registry."""
    return _registry


def register_extension(manifest: ExtensionManifest) -> None:
    """Register an extension into the global registry."""
    _registry.register_extension(manifest)


def unregister_extension(extension_id: str) -> bool:
    """Unregister an extension from the global registry."""
    return _registry.unregister_extension(extension_id)


def enable_extension(extension_id: str) -> bool:
    """Enable an extension in the global registry."""
    return _registry.enable_extension(extension_id)


def disable_extension(extension_id: str) -> bool:
    """Disable an extension in the global registry."""
    return _registry.disable_extension(extension_id)


def is_extension_enabled(extension_id: str) -> bool:
    """Check if an extension is enabled."""
    return _registry.is_enabled(extension_id)


def list_extensions( category: Optional[str] = None) -> List[ExtensionManifest]:
    """List all extensions."""
    return _registry.list_extensions(category)


def install_extension(manifest: ExtensionManifest,
                      all_extensions: Dict[str, ExtensionManifest]) -> Dict[str, any]:
    """Attempt to install an extension."""
    return _registry.install_extension(manifest, all_extensions)