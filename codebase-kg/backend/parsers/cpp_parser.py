"""Tree-sitter-based C++ parser returning unified IR.

Uses tree-sitter-cpp grammar for robust C++ analysis, returning data compatible
with the unified IR schema.
"""

import os
from typing import List
import tree_sitter as ts
import tree_sitter_cpp as tcp
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


class CppParser(ParserInterface):
    """Tree-sitter-based C++ analyzer returning unified IR."""

    name = "cpp"
    extensions = (".cpp", ".hpp", ".hpp", ".cc", ".cxx")
    capability = "full"

    def analyze_file(self, file_path: str) -> ParsedFileIR:
        """Analyze a C++ file using tree-sitter and return unified IR."""
        try:
            language = ts.Language(tcp.language())
            parser = ts.Parser(language)
        except Exception:
            return ParsedFileIR(
                path=file_path,
                errors=["tree-sitter-cpp grammar not available"],
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

        # Namespace definitions
        if node_type == "namespace_definition":
            name_node = self._find_child_by_type(node, "namespace_identifier")
            name = self._get_identifier_text(name_node, source_code) or ""

            # Treat namespace as a class-like container
            cls = ClassIR(
                name=name,
                line=start_row,
                column=start_col,
                base_classes=[],
            )
            classes.append(cls)

        # Namespace aliases (using directive)
        elif node_type == "using_directive":
            name_node = self._find_child_by_type(node, "namespace_identifier")
            name = self._get_identifier_text(name_node, source_code) or ""
            # Record as symbol
            symbols.append(
                SymbolIR(
                    name=name,
                    kind="namespace",
                    location=SourceLocation(
                        file=file_path,
                        line=start_row,
                        column=start_col,
                    ),
                    evidence="using_directive",
                )
            )

        # Struct definitions
        elif node_type == "struct_specifier":
            name_node = self._find_child_by_type(node, "type_identifier")
            name = self._get_identifier_text(name_node, source_code) or ""

            # Find field declarations
            fields: List[str] = []
            for child in node.children:
                if child.type == "access_specifier":
                    for member in child.children:
                        if member.type == "field_declarator":
                            fname = self._find_child_by_type(member, "identifier")
                            if fname:
                                fname_text = self._get_identifier_text(fname, source_code) or ""
                                if fname_text:
                                    fields.append(fname_text)

            cls = ClassIR(
                name=name,
                line=start_row,
                column=start_col,
                base_classes=fields,
            )
            classes.append(cls)

        # Class declarations
        elif node_type == "class_declaration":
            name_node = self._find_child_by_type(node, "type_identifier")
            name = self._get_identifier_text(name_node, source_code) or ""

            # Find base classes / inherits
            base_classes: List[str] = []
            for child in node.children:
                if child.type == "base_class":
                    base_name = self._find_child_by_type(child, "type_identifier")
                    if base_name:
                        bname = self._get_identifier_text(base_name, source_code) or ""
                        if bname and bname not in base_classes:
                            base_classes.append(bname)

            cls = ClassIR(
                name=name,
                line=start_row,
                column=start_col,
                base_classes=base_classes,
            )
            classes.append(cls)

        # Enum definitions
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

            # Also add enum constants
            for child in node.children:
                if child.type == "enum_body":
                    for enum_item in child.children:
                        if enum_item.type == "enum_item":
                            name_node = self._find_child_by_type(
                                enum_item, "identifier"
                            )
                            cname = self._get_identifier_text(name_node, source_code) or ""
                            if cname:
                                symbols.append(
                                    SymbolIR(
                                        name=cname,
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
            result = CppParser._find_child_by_type(child, target_type)
            if result:
                return result
        return None