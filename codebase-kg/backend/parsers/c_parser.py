"""Tree-sitter-based C parser returning unified IR.

Uses tree-sitter-c grammar for robust C analysis, returning data compatible
with the unified IR schema.
"""

import os
from typing import List
import tree_sitter as ts
import tree_sitter_c as tc
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


class CParser(ParserInterface):
    """Tree-sitter-based C analyzer returning unified IR."""

    name = "c"
    extensions = (".c", ".h")
    capability = "full"

    def analyze_file(self, file_path: str) -> ParsedFileIR:
        """Analyze a C file using tree-sitter and return unified IR."""
        try:
            language = ts.Language(tc.language())
            parser = ts.Parser(language)
        except Exception:
            return ParsedFileIR(
                path=file_path,
                errors=["tree-sitter-c grammar not available"],
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

        # Preprocessor include
        if node_type == "preproc_include":
            for child in node.children:
                if child.type == "system_lib_string":
                    mod = self._get_identifier_text(child, source_code) or ""
                    if mod:
                        imports.append(
                            ImportIR(
                                module=mod,
                                is_local=False,
                                line=start_row,
                                kind="import",
                                unresolved=True,
                            )
                        )

        # Struct definitions
        elif node_type == "struct_specifier":
            name_node = self._find_child_by_type(node, "type_identifier")
            name = self._get_identifier_text(name_node, source_code) or ""

            # Find field declarations
            fields: List[str] = []
            for child in node.children:
                if child.type == "field_declaration":
                    for field_child in child.children:
                        if field_child.type == "type_identifier":
                            fname = self._get_identifier_text(field_child, source_code) or ""
                            if fname:
                                fields.append(fname)

            cls = ClassIR(
                name=name,
                line=start_row,
                column=start_col,
                base_classes=fields,  # Fields treated as "base" in C structs
            )
            classes.append(cls)

        # Enum definitions
        elif node_type == "enum_specifier":
            name_node = self._find_child_by_type(node, "identifier")
            name = self._get_identifier_text(name_node, source_code) or ""

            constants: List[str] = []
            for child in node.children:
                if child.type == "enumerator":
                    const_name = self._find_child_by_type(child, "identifier")
                    if const_name:
                        cname = self._get_identifier_text(const_name, source_code) or ""
                        if cname:
                            constants.append(cname)

            symbols.append(
                SymbolIR(
                    name=name,
                    kind="enum",
                    location=SourceLocation(
                        file=file_path,
                        line=start_row,
                        column=start_col,
                    ),
                    evidence="enum_specifier",
                )
            )

            for const in constants:
                symbols.append(
                    SymbolIR(
                        name=const,
                        kind="constant",
                        location=SourceLocation(
                            file=file_path,
                            line=start_row,
                            column=start_col,
                        ),
                        evidence="enum_constant",
                    )
                )

        # Function definitions
        elif node_type == "function_definition":
            # Return type
            return_type_node = self._find_child_by_type(node, "type_specifier")
            return_type = self._get_identifier_text(return_type_node, source_code) or ""

            # Function name
            name_node = self._find_child_by_type(node, "declarator")
            name = self._get_identifier_text(name_node, source_code) or "" if name_node else ""

            # Parameters
            param_count = 0
            for child in node.children:
                if child.type == "parameter_list":
                    param_count = len(
                        [c for c in child.children if c.type == "identifier"]
                    )

            # Check if static
            is_static = any(child.type == "static_storage_class" for child in node.children)

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

        # Typedef definitions
        elif node_type == "type_definition":
            name_node = self._find_child_by_type(node, "declarator")
            name = self._get_identifier_text(name_node, source_code) or ""

            symbols.append(
                SymbolIR(
                    name=name,
                    kind="typedef",
                    location=SourceLocation(
                        file=file_path,
                        line=start_row,
                        column=start_col,
                    ),
                    evidence="typedef",
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
            result = CParser._find_child_by_type(child, target_type)
            if result:
                return result
        return None