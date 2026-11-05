"""Python source code analyzer using AST for import/function/class extraction."""

import ast
import os
from typing import Dict, List, Set, Tuple, Optional, Any
from pathlib import Path


class PythonAnalyzer:
    """Analyzes Python source files using the ast module."""

    def __init__(self, project_root: str = ""):
        self.project_root = os.path.normpath(project_root)
        self.imports: List[Dict[str, Any]] = []
        self.functions: List[Dict[str, Any]] = []
        self.classes: List[Dict[str, Any]] = []
        self.unresolved_imports: List[str] = []

    def analyze_file(self, file_path: str) -> Dict[str, Any]:
        """Analyze a single Python file and extract dependencies and symbols."""
        self.imports = []
        self.functions = []
        self.classes = []
        self.unresolved_imports = []

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                source_code = f.read()
        except (OSError, UnicodeDecodeError):
            return {
                "imports": [],
                "functions": [],
                "classes": [],
                "unresolved_imports": [],
            }

        try:
            tree = ast.parse(source_code, filename=file_path)
        except SyntaxError:
            # Return empty results for files with syntax errors
            return {
                "imports": [],
                "functions": [],
                "classes": [],
                "unresolved_imports": [],
            }

        self._visit_ast(tree)

        return {
            "imports": self.imports,
            "functions": self.functions,
            "classes": self.classes,
            "unresolved_imports": self.unresolved_imports,
            "source_code": source_code,
        }

    def _visit_ast(self, tree: ast.AST):
        """Walk the AST and extract relevant information."""
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                self._handle_import(node)
            elif isinstance(node, ast.ImportFrom):
                self._handle_from_import(node)
            elif isinstance(node, ast.FunctionDef):
                self._handle_function_def(node)
            elif isinstance(node, ast.ClassDef):
                self._handle_class_def(node)

    def _handle_import(self, node: ast.Import):
        """Handle a standard import statement (import foo)."""
        module_names = [alias.name for alias in node.names]
        for module_name in module_names:
            # Check if it's a local module or external package
            is_local = self._is_local_module(module_name)
            self.imports.append({
                "type": "import",
                "module": module_name,
                "is_local": is_local,
                "line": node.lineno,
                "original": node.lineno,
            })
            if not is_local:
                self.unresolved_imports.append(module_name)

    def _handle_from_import(self, node: ast.ImportFrom):
        """Handle a from-import statement (from foo import bar)."""
        module = node.module or ""
        is_local = self._is_local_module(module)

        result = {
            "type": "from_import",
            "module": module,
            "is_local": is_local,
            "names": [alias.name for alias in node.names],
            "level": node.level,  # For relative imports
            "line": node.lineno,
        }

        # Handle relative imports
        if node.level > 0:
            result["relative"] = True
            result["module"] = f"level_{node.level}"
            # Relative imports are internal; mark as local
            is_local = True

        # Track unresolved imports for names that can't be resolved locally
        for alias in node.names:
            if alias.name not in ["__builtins__"] and not is_local:
                self.unresolved_imports.append(alias.name)

        self.imports.append(result)

    def _is_local_module(self, module_name: str) -> bool:
        """Check if a module name refers to a local project file."""
        if not module_name:
            return False

        # Remove common suffixes
        name = module_name.split(".")[0]

        # Check against known Python standard library modules
        stdlib_modules = {
            "os", "sys", "json", "math", "datetime", "collections", "itertools",
            "functools", "pathlib", "uuid", "tempfile", "hashlib", "subprocess",
            "re", "xml", "json", "io", "csv", "configparser", "argparse",
            "warnings", "copy", "pprint", "textwrap", "strenum", "dataclasses",
            "typing", "enum", "abc", "io", "filecmp", "shutil", "glob",
            "tempfile", "linecache", "runpy", "pickle", "shelve", "queue",
            "threading", "multiprocessing", "concurrent", "weakref",
            "collections.abc", "stat", "fileinput", "linecache",
        }

        # Check if it's a standard library module
        base_name = module_name.split(".")[0]
        if base_name in stdlib_modules:
            return False

        # Check if it matches a file in the project root
        # Look for .py files
        possible_paths = [
            os.path.join(self.project_root, f"{name}.py"),
            os.path.join(self.project_root, name, "__init__.py"),
        ]

        # Also check with .mjs, .cjs extensions for JS interop
        for path in possible_paths:
            if os.path.exists(path):
                return True

        # Special case: __init__ files and package paths
        if name in self.project_root or module_name.startswith(self.project_root):
            return True

        return False

    def _handle_function_def(self, node: ast.FunctionDef):
        """Handle a function definition."""
        # Skip dunder methods for cleaner output, but keep them as they may be relevant
        is_relative = False

        func_info = {
            "name": node.name,
            "line": node.lineno,
            "col": node.col_offset,
            "args": [arg.arg for arg in node.args.args],
            "is_async": getattr(node, 'is_async', False),
            "is_generator": node.body and any(isinstance(n, ast.Yield) for n in ast.walk(node)),
            "decorators": [
                dec.id for dec in node.decorator_list if isinstance(dec, ast.Name)
            ],
        }

        # Check if this is a relative import (unlikely at function level, but check decorators)
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name):
                if dec.func.name.startswith("_"):
                    is_relative = True

        self.functions.append(func_info)

    def _handle_class_def(self, node: ast.ClassDef):
        """Handle a class definition."""
        class_info = {
            "name": node.name,
            "line": node.lineno,
            "col": node.col_offset,
            "base_classes": [base.id if isinstance(base, ast.Name) else "" for base in node.bases],
            "decorators": [
                dec.id for dec in node.decorator_list if isinstance(dec, ast.Name)
            ],
        }
        self.classes.append(class_info)