"""Tree-sitter-based Dart parser returning unified IR.

Uses tree-sitter-dart grammar for robust Dart/Flutter analysis, returning data
compatible with the unified IR schema.
"""

import os
from typing import List
import tree_sitter as ts
import tree_sitter_dart as tdart
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


class DartParser(ParserInterface):
    """Tree-sitter-based Dart analyzer returning unified IR."""

    name = "dart"
    extensions = (".dart",)
    capability = "full"

    def analyze_file(self, file_path: str) -> ParsedFileIR:
        """Analyze a Dart file using tree-sitter and return unified IR."""
        try:
            language = ts.Language(tdart.language())
            parser = ts.Parser(language)
        except Exception:
            return ParsedFileIR(
                path=file_path,
                errors=["tree-sitter-dart grammar not available"],
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
        start_row = node.start_point.row
        start_col = node.start_point.column

        # Import directives
        if node_type == "import_or_export":
            # Could be import or export
            for child in node.children:
                if child.type == "library_import":
                    # tree-sitter-dart represents imports here
                    for imp in child.children:
                        if imp.type == "import_specification":
                            # Get the URI
                            uri_node = None
                            for sub in imp.children:
                                if sub.type == "configurable_uri":
                                    for inner in sub.children:
                                        if inner.type == "uri":
                                            uri_node = inner
                                            break
                            if uri_node:
                                uri_text = self._get_identifier_text(uri_node, source_code) or ""
                                module_name = (
                                    uri_text.split("/")[-1].replace(".dart", "")
                                    if uri_text
                                    else ""
                                )
                                if module_name:
                                    is_local = self._is_local_module(module_name)
                                    imports.append(
                                        ImportIR(
                                            module=module_name,
                                            is_local=is_local,
                                            line=start_row,
                                            kind="import",
                                            unresolved=not is_local and module_name,
                                        )
                                    )
                                    if not is_local and module_name:
                                        unresolved.append(module_name)

        # Function declarations / function expressions
        elif node_type == "function_signature":
            name_node = self._find_child_by_type(node, "identifier")
            name = self._get_identifier_text(name_node, source_code) or ""

            # Count parameters
            param_count = 0
            for child in node.children:
                if child.type == "formal_parameter_list":
                    param_count = len(
                        [c for c in child.children if c.type == "identifier"]
                    )

            # Check if it's a getter/setter (based on name starting with 'get'/'set')
            is_property = name.startswith("get") or name.startswith("set")

            func = FunctionIR(
                name=name,
                line=start_row,
                column=start_col,
                is_async=False,  # Dart async detected differently
                is_generator=False,
                decorators=[],
                parameters=param_count,
            )
            functions.append(func)

        # Method definitions (inside classes)
        elif node_type == "method_signature":
            name_node = self._find_child_by_type(node, "identifier")
            name = self._get_identifier_text(name_node, source_code) or ""

            # Count parameters
            param_count = 0
            for child in node.children:
                if child.type == "formal_parameter_list":
                    param_count = len(
                        [c for c in child.children if c.type == "identifier"]
                    )

            func = FunctionIR(
                name=name,
                line=start_row,
                column=start_col,
                is_async=False,
                is_generator=False,
                decorators=[],
                parameters=param_count,
            )
            functions.append(func)

        # Class declarations
        elif node_type == "class_declaration":
            name_node = self._find_child_by_type(node, "identifier")
            name = self._get_identifier_text(name_node, source_code) or ""

            # Find superclass / implements
            base_classes: List[str] = []
            for child in node.children:
                if child.type == "superclass":
                    base_name = self._find_child_by_type(child, "identifier")
                    if base_name:
                        bname = self._get_identifier_text(base_name, source_code) or ""
                        if bname and bname not in base_classes:
                            base_classes.append(bname)
                elif child.type == "interfaces":
                    for iface in child.children:
                        if iface.type == "type_identifier":
                            base_name = self._get_identifier_text(iface, source_code) or ""
                            if base_name and base_name not in base_classes:
                                base_classes.append(base_name)

            cls = ClassIR(
                name=name,
                line=start_row,
                column=start_col,
                base_classes=base_classes,
            )
            classes.append(cls)

        # Enum declarations
        elif node_type == "enum_declaration":
            for child in node.children:
                if child.type == "enum_body":
                    for enum_item in child.children:
                        if enum_item.type == "enum_constant":
                            name_node = self._find_child_by_type(
                                enum_item, "identifier"
                            )
                            name = self._get_identifier_text(name_node, source_code) or ""
                            if name:
                                symbols.append(
                                    SymbolIR(
                                        name=name,
                                        kind="enum",
                                        location=SourceLocation(
                                            file=file_path,
                                            line=start_row,
                                            column=start_col,
                                        ),
                                        evidence="enum_declaration",
                                    )
                                )

                            # Also add the constant
                            if name:
                                symbols.append(
                                    SymbolIR(
                                        name=name,
                                        kind="constant",
                                        location=SourceLocation(
                                            file=file_path,
                                            line=start_row,
                                            column=start_col,
                                        ),
                                        evidence="enum_constant",
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
            result = DartParser._find_child_by_type(child, target_type)
            if result:
                return result
        return None

    @staticmethod
    def _is_local_module(module_name: str) -> bool:
        """Check if a module specifier points inside the project."""
        if not module_name:
            return False

        if module_name.startswith(("./", "../", "/")):
            return True

        if module_name.startswith(("@/", "~/", "src/")):
            return True

        # A bare specifier is local only if a matching file actually exists.
        if not module_name.startswith("@") and not module_name.startswith("."):
            # Check Dart extensions
            for ext in (".dart",):
                if os.path.exists(module_name + ext):
                    return True

        return False