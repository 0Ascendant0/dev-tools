"""Tree-sitter-based JavaScript/TypeScript parser returning unified IR.

Uses tree-sitter grammars for JS/TS analysis, returning data compatible
with the unified IR schema.
"""

import os
from typing import List
import tree_sitter as ts
import tree_sitter_javascript as tjs
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


class JavaScriptTsParser(ParserInterface):
    """Tree-sitter-based JavaScript/TypeScript analyzer returning unified IR."""

    name = "javascript"
    extensions = (".js", ".jsx", ".mjs", ".cjs")
    capability = "full"

    def analyze_file(self, file_path: str) -> ParsedFileIR:
        """Analyze a JS/TS file using tree-sitter and return unified IR."""
        try:
            language = ts.Language(tjs.language())
            parser = ts.Parser(language)
        except Exception:
            return ParsedFileIR(
                path=file_path,
                errors=["tree-sitter-javascript grammar not available"],
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

        # Import statements (ESM and CommonJS)
        if node_type == "import_statement":
            module_name = ""
            imported_names: List[str] = []
            for child in node.children:
                if child.type == "string":
                    module_name = self._get_identifier_text(child, source_code) or ""
                elif child.type == "named_imports":
                    for imp in child.children:
                        if imp.type == "import_specifier":
                            imported_names.append(
                                self._get_identifier_text(imp, source_code) or ""
                            )
                elif child.type == "identifier":
                    imported_names.append(
                        self._get_identifier_text(child, source_code) or ""
                    )

            is_local = self._is_local_module(module_name)
            kind = "esm_import" if not module_name.startswith("require(") else "commonjs_require"
            imports.append(
                ImportIR(
                    module=module_name,
                    is_local=is_local,
                    line=start_row,
                    kind=kind,
                    unresolved=not is_local and module_name,
                    names=imported_names if imported_names else None,
                )
            )
            if not is_local and module_name:
                unresolved.append(module_name)

        # Export statements
        elif node_type == "export_statement":
            # Determine export kind
            export_name = ""
            is_default = False
            is_named = False

            for child in node.children:
                if child.type == "identifier":
                    export_name = self._get_identifier_text(child, source_code) or ""
                elif child.type == "default_export":
                    is_default = True
                elif child.type == "named_exports":
                    is_named = True
                    for exp in child.children:
                        if exp.type == "export_specifier":
                            name = self._get_identifier_text(exp, source_code) or ""
                            if name:
                                exports.append(
                                    ExportIR(
                                        name=name,
                                        kind="export_named",
                                        line=start_row,
                                    )
                                )

            if is_default and export_name:
                exports.append(
                    ExportIR(
                        name=export_name,
                        kind="export_default",
                        line=start_row,
                    )
                )
            elif is_named and export_name:
                exports.append(
                    ExportIR(
                        name=export_name,
                        kind="export_list",
                        line=start_row,
                    )
                )

        # Function declarations
        elif node_type == "function_definition":
            name_node = self._find_child_by_type(node, "identifier")
            name = self._get_identifier_text(name_node, source_code) or ""

            is_async = any(
                child.type == "async" for child in node.children
            )

            # Count parameters
            param_count = 0
            for child in node.children:
                if child.type == "parameter_list":
                    param_count = len(
                        [c for c in child.children if c.type == "identifier"]
                    )

            func = FunctionIR(
                name=name,
                line=start_row,
                column=start_col,
                is_async=is_async,
                is_generator=self._has_yield(node),
                parameters=param_count,
            )
            functions.append(func)

        # Class declarations
        elif node_type == "class_declaration":
            name_node = self._find_child_by_type(node, "identifier")
            name = self._get_identifier_text(name_node, source_code) or ""

            # Find base class / extends
            base_classes: List[str] = []
            for child in node.children:
                if child.type == "base_clause":
                    for inner in child.children:
                        if inner.type == "type_identifier":
                            base_name = self._get_identifier_text(inner, source_code) or ""
                            if base_name:
                                base_classes.append(base_name)

            cls = ClassIR(
                name=name,
                line=start_row,
                column=start_col,
                base_classes=base_classes,
            )
            classes.append(cls)

        # Enum declarations (TypeScript)
        elif node_type == "enum_declaration":
            for child in node.children:
                if child.type == "enum_body":
                    for enum_item in child.children:
                        if enum_item.type == "enum_item":
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
            result = JavaScriptTsParser._find_child_by_type(child, target_type)
            if result:
                return result
        return None

    @staticmethod
    def _has_yield(node: ts.Node) -> bool:
        """Check if a function contains a yield."""
        for child in node.children:
            if child.type == "yield_expression":
                return True
        return False

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
            # Check common extensions
            for ext in (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"):
                if os.path.exists(module_name + ext):
                    return True

        return False