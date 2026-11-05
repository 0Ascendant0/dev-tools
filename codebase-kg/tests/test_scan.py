"""Tests for file discovery and local import resolution."""

import os

from api.scan import (
    DEFAULT_EXCLUSIONS,
    discover_source_files,
    resolve_local_import,
    should_exclude,
)


def make_tree(tmp_path):
    files = {
        "main.py": "",
        "pkg/__init__.py": "",
        "pkg/models.py": "",
        "src/App.jsx": 'import Button from "./Button";',
        "src/Button.jsx": "export default function Button() {}",
        "src/utils/math.js": "export const add = (a, b) => a + b;",
        "src/index.ts": "export const x = 1;",
        "node_modules/react/index.js": "module.exports = {};",
        ".git/hooks/pre-commit.py": "",
        "__pycache__/cached.py": "",
        "dist/bundle.js": "",
        "README.md": "",
    }
    for relative, content in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return tmp_path


def test_discover_source_files_skips_excluded_and_unsupported(tmp_path):
    root = make_tree(tmp_path)
    found = {
        os.path.relpath(path, root).replace(os.sep, "/")
        for path in discover_source_files(str(root))
    }

    assert "main.py" in found
    assert "pkg/models.py" in found
    assert "src/App.jsx" in found
    assert "src/utils/math.js" in found
    assert "src/index.ts" in found

    assert not any("node_modules" in path for path in found)
    assert not any(path.startswith(".git/") for path in found)
    assert not any("__pycache__" in path for path in found)
    assert not any(path.startswith("dist/") for path in found)
    assert "README.md" not in found


def test_should_exclude_matches_nested_directories():
    assert should_exclude(os.path.join("root", "node_modules", "x.js"), DEFAULT_EXCLUSIONS)
    assert not should_exclude(os.path.join("root", "src", "x.js"), DEFAULT_EXCLUSIONS)


def test_resolve_relative_js_import_without_extension(tmp_path):
    root = make_tree(tmp_path)
    known = {
        os.path.relpath(path, root).replace(os.sep, "/")
        for path in discover_source_files(str(root))
    }

    assert (
        resolve_local_import(str(root), "src/App.jsx", "./Button", known)
        == "src/Button.jsx"
    )
    assert (
        resolve_local_import(str(root), "src/App.jsx", "./utils/math", known)
        == "src/utils/math.js"
    )


def test_resolve_python_dotted_module(tmp_path):
    root = make_tree(tmp_path)
    known = {
        os.path.relpath(path, root).replace(os.sep, "/")
        for path in discover_source_files(str(root))
    }

    assert resolve_local_import(str(root), "main.py", "pkg.models", known) == "pkg/models.py"


def test_resolve_leaves_external_and_missing_imports_unresolved(tmp_path):
    root = make_tree(tmp_path)
    known = {
        os.path.relpath(path, root).replace(os.sep, "/")
        for path in discover_source_files(str(root))
    }

    assert resolve_local_import(str(root), "main.py", "requests", known) is None
    assert resolve_local_import(str(root), "src/App.jsx", "./missing", known) is None
    assert resolve_local_import(str(root), "src/App.jsx", "../../outside", known) is None