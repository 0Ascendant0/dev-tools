"""JavaScript/TypeScript source code analyzer for import/export/function/class extraction."""

import os
import re
from typing import Any, Dict, List, Optional, Set

# import x from "m" / import {a, b} from "m" / import * as ns from "m" / import "m"
IMPORT_RE = re.compile(
    r"""import\s+(?:[\w*{}\s,$]+\s+from\s+)?['"]([^'"]+)['"]""",
    re.MULTILINE,
)
# export { a } from "m" / export * from "m"
EXPORT_FROM_RE = re.compile(
    r"""export\s+(?:\*(?:\s+as\s+\w+)?|\{[^}]*\})\s+from\s+['"]([^'"]+)['"]""",
    re.MULTILINE,
)
REQUIRE_RE = re.compile(r"""require\(\s*['"]([^'"]+)['"]\s*\)""")

FUNCTION_DECL_RE = re.compile(
    r"""(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*(\w+)\s*\("""
)
ARROW_ASSIGN_RE = re.compile(
    r"""(?:export\s+)?(?:const|let|var)\s+(\w+)\s*(?::\s*[^=]+?)?=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*=>"""
)
FUNCTION_ASSIGN_RE = re.compile(
    r"""(?:export\s+)?(?:const|let|var)\s+(\w+)\s*(?::\s*[^=]+?)?=\s*(?:async\s+)?function\b"""
)
CLASS_DECL_RE = re.compile(
    r"""(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+(\w+)"""
)
EXPORT_NAME_RE = re.compile(
    r"""export\s+(?:default\s+)?(?:async\s+)?(?:function|class|const|let|var|interface|type|enum)\s+(\w+)"""
)
EXPORT_LIST_RE = re.compile(r"""export\s*\{([^}]*)\}""")
EXPORTS_PROP_RE = re.compile(r"""exports\.(\w+)""")

# Reserved words that regexes may pick up as identifiers.
RESERVED = {
    "if", "for", "while", "switch", "catch", "function", "return", "new",
    "typeof", "require", "module", "exports", "import", "export",
}


def _strip_comments(source: str) -> str:
    """Remove // and /* */ comments without touching string literals."""
    out = []
    i = 0
    length = len(source)
    quote: Optional[str] = None

    while i < length:
        char = source[i]

        if quote:
            out.append(char)
            if char == "\\" and i + 1 < length:
                out.append(source[i + 1])
                i += 2
                continue
            if char == quote:
                quote = None
            i += 1
            continue

        if char in "\"'`":
            quote = char
            out.append(char)
            i += 1
            continue

        if source.startswith("//", i):
            newline = source.find("\n", i)
            i = length if newline == -1 else newline
            continue

        if source.startswith("/*", i):
            end = source.find("*/", i + 2)
            i = length if end == -1 else end + 2
            continue

        out.append(char)
        i += 1

    return "".join(out)


class JavaScriptAnalyzer:
    """Analyzes JavaScript and TypeScript source files."""

    def __init__(self, project_root: str = ""):
        self.project_root = os.path.normpath(project_root)
        self.imports: List[Dict[str, Any]] = []
        self.exports: List[Dict[str, Any]] = []
        self.functions: List[Dict[str, Any]] = []
        self.classes: List[Dict[str, Any]] = []
        self.unresolved_imports: List[str] = []

    def analyze_file(self, file_path: str) -> Dict[str, Any]:
        """Analyze a single JavaScript/TypeScript file."""
        self.imports = []
        self.exports = []
        self.functions = []
        self.classes = []
        self.unresolved_imports = []

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as handle:
                raw_source = handle.read()
        except OSError:
            return self._result()

        source = _strip_comments(raw_source)
        self._extract_imports(source)
        self._extract_exports(source)
        self._extract_functions(source)
        self._extract_classes(source)

        return self._result()

    def _result(self) -> Dict[str, Any]:
        return {
            "imports": self.imports,
            "exports": self.exports,
            "functions": self.functions,
            "classes": self.classes,
            "unresolved_imports": self.unresolved_imports,
        }

    # -- extraction ---------------------------------------------------------

    def _add_import(self, module_name: str, line: int, kind: str):
        module_name = module_name.strip()
        if not module_name:
            return
        is_local = self._is_local_module(module_name)
        self.imports.append({
            "type": kind,
            "module": module_name,
            "is_local": is_local,
            "line": line,
            "original": module_name,
        })
        if is_local and module_name not in self.unresolved_imports:
            self.unresolved_imports.append(module_name)

    def _extract_imports(self, source: str):
        for match in IMPORT_RE.finditer(source):
            self._add_import(
                match.group(1), source.count("\n", 0, match.start()) + 1, "esm_import"
            )
        for match in EXPORT_FROM_RE.finditer(source):
            self._add_import(
                match.group(1), source.count("\n", 0, match.start()) + 1, "esm_reexport"
            )
        for match in REQUIRE_RE.finditer(source):
            self._add_import(
                match.group(1), source.count("\n", 0, match.start()) + 1, "commonjs_require"
            )

    def _extract_exports(self, source: str):
        seen: Set[str] = set()

        for match in EXPORT_NAME_RE.finditer(source):
            name = match.group(1)
            if name not in seen:
                seen.add(name)
                self.exports.append({
                    "type": "export_named",
                    "name": name,
                    "line": source.count("\n", 0, match.start()) + 1,
                })

        for match in EXPORT_LIST_RE.finditer(source):
            for part in match.group(1).split(","):
                # "foo" or "foo as bar"
                name = part.strip().split(" as ")[-1].strip()
                if name and name not in seen:
                    seen.add(name)
                    self.exports.append({
                        "type": "export_list",
                        "name": name,
                        "line": source.count("\n", 0, match.start()) + 1,
                    })

        if re.search(r"export\s+default\b", source):
            self.exports.append({
                "type": "export_default",
                "line": source.count("\n", 0, source.find("export default")) + 1,
            })

        if "module.exports" in source:
            self.exports.append({
                "type": "module_exports",
                "line": source.count("\n", 0, source.find("module.exports")) + 1,
            })

        for match in EXPORTS_PROP_RE.finditer(source):
            name = match.group(1)
            if name.startswith("__") or name in seen:
                continue
            seen.add(name)
            self.exports.append({
                "type": "exports_property",
                "name": name,
                "line": source.count("\n", 0, match.start()) + 1,
            })

    def _extract_functions(self, source: str):
        seen: Set[str] = set()

        def add(name: str, line: int, is_arrow: bool):
            if not name or name in RESERVED or name in seen:
                return
            seen.add(name)
            self.functions.append({
                "name": name,
                "line": line,
                "col": 0,
                "is_arrow": is_arrow,
                "is_component": name[:1].isupper(),
            })

        for match in FUNCTION_DECL_RE.finditer(source):
            add(match.group(1), source.count("\n", 0, match.start()) + 1, False)

        for match in ARROW_ASSIGN_RE.finditer(source):
            add(match.group(1), source.count("\n", 0, match.start()) + 1, True)

        for match in FUNCTION_ASSIGN_RE.finditer(source):
            add(match.group(1), source.count("\n", 0, match.start()) + 1, False)

    def _extract_classes(self, source: str):
        seen: Set[str] = set()
        for match in CLASS_DECL_RE.finditer(source):
            name = match.group(1)
            if name in RESERVED or name in seen:
                continue
            seen.add(name)
            self.classes.append({
                "name": name,
                "line": source.count("\n", 0, match.start()) + 1,
            })

    # -- resolution ---------------------------------------------------------

    def _is_local_module(self, module_name: str) -> bool:
        """Check if a module specifier points inside the project."""
        if not module_name:
            return False

        if module_name.startswith(("./", "../", "/")):
            return True

        # Path aliases commonly used by bundlers
        if module_name.startswith(("@/", "~/", "src/")):
            return True

        if not self.project_root:
            return False

        # A bare specifier is local only if a matching file actually exists.
        relative = os.path.join(self.project_root, module_name)
        if os.path.exists(relative):
            return True

        for ext in (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"):
            if os.path.exists(relative + ext):
                return True

        return False