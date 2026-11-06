"""Tree-sitter-based Python parser returning unified IR.

This parser uses tree-sitter-python grammar for robust Python source analysis,
returning data compatible with the unified IR schema defined in ir_schema.py.
"""

import os
from typing import List
import tree_sitter as ts
import tree_sitter_python as tsp
from ir_schema import (
    ParsedFileIR,
    SymbolIR,
    ImportIR,
    ExportIR,
    FunctionIR,
    ClassIR,
    SourceLocation,
    ParserInterface,
)


class PythonTsParser(ParserInterface):
    """Tree-sitter-based Python analyzer returning unified IR."""

    name = "python"
    extensions = (".py",)
    capability = "full"

    def analyze_file(self, file_path: str) -> ParsedFileIR:
        """Analyze a Python file using tree-sitter and return unified IR."""
        try:
            language = ts.Language(tsp.language())
            parser = ts.Parser(language)
        except Exception:
            return ParsedFileIR(
                path=file_path,
                errors=["tree-sitter-python grammar not available"],
            )

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                source_code = f.read()
        except OSError:
            return ParsedFileIR(path=file_path)

        tree = parser.parse(source_code.encode("utf-8"))

        return self._extract_ir(file_path, source_code, tree)

    def _extract_ir(self, file_path: str, source_code: str, tree: ts.Tree) -> ParsedFileIR:
        """Extract IR elements from a tree-sparse parse tree."""
        root = tree.root_node

        symbols: List[SymbolIR] = []
        imports: List[ImportIR] = []
        exports: List[ExportIR] = []
        functions: List[FunctionIR] = []
        classes: List[ClassIR] = []
        unresolved: List[str] = []
        errors: List[str] = []

        # Walk the tree to extract nodes
        for node in root.children:
            self._walk_node(
                node, source_code, file_path, symbols, imports, exports,
                functions, classes, unresolved, errors
            )

        return ParsedFileIR(
            path=file_path,
            source_code=source_code,
            symbols=symbols,
            imports=imports,
            exports=exports,
            functions=functions,
            classes=classes,
            unresolved=unresolved,
            errors=errors,
        )

    def _walk_node(
        self,
        node: ts.Node,
        source_code: str,
        file_path: str,
        symbols: List[SymbolIR],
        imports: List[ImportIR],
        exports: List[ExportIR],
        functions: List[FunctionIR],
        classes: List[ClassIR],
        unresolved: List[str],
        errors: List[str],
    ):
        """Recursively walk tree-sitter nodes and extract IR data."""

        node_type = node.type

        # Import statements
        if node_type == "import_statement":
            # Get the module name from the import
            for child in node.children:
                if child.type == "dotted_name":
                    module_name = self._get_identifier_text(child, source_code)
                    if module_name:
                        is_local = self._is_local_module(module_name)
                        imports.append(
                            ImportIR(
                                module=module_name,
                                is_local=is_local,
                                line=node.start_point.row,
                                kind="import",
                                unresolved=not is_local,
                            )
                        )
                        if not is_local:
                            unresolved.append(module_name)

        elif node_type == "import_from_statement":
            # from X import Y
            module_name = ""
            imported_names: List[str] = []
            for child in node.children:
                if child.type == "module_name":
                    module_name = self._get_identifier_text(child, source_code) or ""
                elif child.type == "dotted_name":
                    imported_names.append(
                        self._get_identifier_text(child, source_code) or ""
                    )
                elif child.type == "identifier":
                    imported_names.append(self._get_identifier_text(child, source_code) or "")

            is_local = self._is_local_module(module_name) if module_name else False
            imports.append(
                ImportIR(
                    module=module_name,
                    is_local=is_local,
                    line=node.start_point.row,
                    kind="from_import",
                    names=imported_names if imported_names else None,
                    unresolved=not is_local and module_name,
                )
            )
            if not is_local and module_name:
                unresolved.append(module_name)

        # Function definitions
        elif node_type == "function_definition":
            name_node = self._find_child_by_type(node, "identifier")
            name = self._get_identifier_text(name_node, source_code) or ""

            # Determine if async
            is_async = any(
                child.type == "async_function" for child in node.children
            )

            # Find parameters
            param_count = 0
            for child in node.children:
                if child.type == "parameters":
                    param_count = len(
                        [c for c in child.children if c.type == "identifier"]
                    )

            func = FunctionIR(
                name=name,
                line=node.start_point.row,
                column=node.start_point.column,
                is_async=is_async,
                is_generator=self._has_yield(node),
                parameters=param_count,
            )
            functions.append(func)

        # Class definitions
        elif node_type == "class_definition":
            name_node = self._find_child_by_type(node, "identifier")
            name = self._get_identifier_text(name_node, source_code) or ""

            # Find base classes
            base_classes: List[str] = []
            for child in node.children:
                if child.type == "base_class":
                    base_name = self._get_identifier_text(
                        child.children[0] if child.children else None, source_code
                    )
                    if base_name:
                        base_classes.append(base_name)

            cls = ClassIR(
                name=name,
                line=node.start_point.row,
                column=node.start_point.column,
                base_classes=base_classes,
            )
            classes.append(cls)

        # Variable/constant assignments at module level
        elif node_type == "assignment":
            # For now, just record simple assignments as variables
            for child in node.children:
                if child.type == "identifier":
                    var_name = self._get_identifier_text(child, source_code)
                    if var_name and var_name not in ("self",):
                        # Check if it's a constant (uppercase)
                        if var_name == var_name.upper():
                            symbols.append(
                                SymbolIR(
                                    name=var_name,
                                    kind="constant",
                                    location=SourceLocation(
                                        file=file_path,
                                        line=node.start_point.row,
                                        column=node.start_point.column,
                                    ),
                                    evidence="assignment",
                                )
                            )
                        else:
                            symbols.append(
                                SymbolIR(
                                    name=var_name,
                                    kind="variable",
                                    location=SourceLocation(
                                        file=file_path,
                                        line=node.start_point.row,
                                        column=node.start_point.column,
                                    ),
                                    evidence="assignment",
                                )
                            )

        # Enum definitions
        elif node_type == "enum_definition":
            for child in node.children:
                if child.type == "enum_body":
                    for enum_item in child.children:
                        if enum_item.type == "enum_item":
                            name_node = enum_item.child_by_field_name("name")
                            if name_node:
                                name = self._get_identifier_text(name_node, source_code) or ""
                                symbols.append(
                                    SymbolIR(
                                        name=name,
                                        kind="enum",
                                        location=SourceLocation(
                                            file=file_path,
                                            line=node.start_point.row,
                                            column=node.start_point.column,
                                        ),
                                        evidence="enum_definition",
                                    )
                                )

        # If this node has children, recurse
        for child in node.children:
            self._walk_node(
                child, source_code, file_path, symbols, imports, exports,
                functions, classes, unresolved, errors
            )

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _get_identifier_text(node: ts.Node, source_code: str) -> str | None:
        """Get the text of an identifier node from source."""
        try:
            return source_code[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
        except Exception:
            return None

    @staticmethod
    def _find_child_by_type(node: ts.Node, target_type: str) -> ts.Node | None:
        """Find first child with the given type."""
        if node.type == target_type:
            return node
        for child in node.children:
            result = PythonTsParser._find_child_by_type(child, target_type)
            if result:
                return result
        return None

    @staticmethod
    def _has_yield(node: ts.Node) -> bool:
        """Check if a function definition contains a yield."""
        # Simple check: look for yield keyword in children
        for child in node.children:
            if child.type == "yield_expression":
                return True
        return False

    @staticmethod
    def _is_local_module(module_name: str) -> bool:
        """Check if a module name refers to a local project file."""
        if not module_name:
            return False

        # Remove common suffixes
        name = module_name.split(".")[0]

        # Check against common Python stdlib modules
        stdlib_modules = {
            "os", "sys", "json", "math", "datetime", "collections", "itertools",
            "functools", "pathlib", "uuid", "tempfile", "hashlib", "subprocess",
            "re", "xml", "io", "csv", "configparser", "argparse",
            "warnings", "copy", "pprint", "textwrap", "dataclasses",
            "typing", "enum", "abc", "shutil", "glob", "filecmp",
        }

        base_name = name.split(".")[0]
        if base_name in stdlib_modules:
            return False

        # Check if file exists in project root
        possible_paths = [
            os.path.join(os.path.dirname(module_name), f"{name}.py"),
        ]

        # Simplified check - in practice we'd need the project root
        # But tree-sitter parsers receive the path from the registry
        if os.path.exists(name + ".py") or os.path.exists(name):
            return True

        return False