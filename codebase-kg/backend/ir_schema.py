"""Unified Intermediate Representation (IR) schema shared across all language parsers.

All parsers must return data compatible with this schema. This ensures the
frontend, graph builder, and analysis tools can work without knowing the
source language.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


# -- Core IR Types -----------------------------------------------------------


@dataclass
class SourceLocation:
    """Positional source location (file, line, column)."""

    file: str
    line: int
    column: int = 0


@dataclass
class SymbolIR:
    """Unified symbol information returned by all parsers."""

    name: str
    kind: str  # "function", "method", "class", "interface", "enum", "variable", "constant"
    location: SourceLocation
    # Evidence: exact source text or tree-sitter node type that identifies this symbol
    evidence: Optional[str] = None
    # Optional parent/container type (class, interface, module)
    container: Optional[str] = None


@dataclass
class ImportIR:
    """Unified import/requirement information."""

    module: str
    is_local: bool
    line: int
    kind: str  # "import", "from_import", "require", "esm_reexport", "commonjs_require"
    unresolved: bool = False
    # For from-imports: the specific names being imported
    names: Optional[List[str]] = None


@dataclass
class ExportIR:
    """Unified export information."""

    name: str
    kind: str  # "export_named", "export_default", "export_list", "module_exports"
    line: int


@dataclass
class FunctionIR:
    """Unified function/method information."""

    name: str
    line: int
    column: int = 0
    is_async: bool = False
    is_generator: bool = False
    decorators: List[str] = field(default_factory=list)
    parameters: int = 0


@dataclass
class ClassIR:
    """Unified class/interface/enum information."""

    name: str
    line: int
    column: int = 0
    base_classes: List[str] = field(default_factory=list)
    decorators: List[str] = field(default_factory=list)


@dataclass
class ParsedFileIR:
    """Complete IR for a single parsed file."""

    path: str
    # Raw source may be stored for reference
    source_code: Optional[str] = None
    # Extracted symbols
    symbols: List[SymbolIR] = field(default_factory=list)
    # Imports (modules depended on)
    imports: List[ImportIR] = field(default_factory=list)
    # Exports (what this module provides)
    exports: List[ExportIR] = field(default_factory=list)
    # Top-level functions
    functions: List[FunctionIR] = field(default_factory=list)
    # Top-level classes
    classes: List[ClassIR] = field(default_factory=list)
    # Unresolved symbols/imports
    unresolved: List[str] = field(default_factory=list)
    # Parse errors encountered
    errors: List[str] = field(default_factory=list)


# -- Parser Interface --------------------------------------------------------

class ParserInterface:
    """Abstract base class that all language parsers must implement.

    Subclasses must implement `analyze_file` returning a ParsedFileIR.
    The returned IR must be compatible with the dataclasses defined in
    this module.
    """

    name: str
    extensions: tuple  # File extensions this parser handles (e.g. (".py",))
    capability: str  # "full", "partial", "unsupported"

    def analyze_file(self, file_path: str) -> ParsedFileIR:
        """Analyze a single file and return unified IR.

        Args:
            file_path: Absolute or relative path to the source file.

        Returns:
            ParsedFileIR containing all extracted information compatible
            with the unified schema.
        """
        raise NotImplementedError("Subclasses must implement analyze_file")

    def can_parse(self, file_path: str) -> bool:
        """Check if this parser can handle the given file by extension."""
        ext = file_path.rsplit(".", 1)[-1] if "." in file_path else ""
        return f".{ext}" in self.extensions


# -- Registry -----------------------------------------------------------------

class ParserRegistry:
    """Central registry of all available language parsers.

    Handles unsupported languages and parser failures without aborting analysis.
    """

    def __init__(self):
        self._parsers: Dict[str, ParserInterface] = {}
        self._by_extension: Dict[str, ParserInterface] = {}

    def register(self, parser: ParserInterface) -> None:
        """Register a parser with the registry.

        The parser's name and extensions are derived from the parser instance.
        """
        self._parsers[parser.name] = parser
        for ext in parser.extensions:
            self._by_extension[ext] = parser

    def get_parser_for_file(self, file_path: str) -> Optional[ParserInterface]:
        """Get the appropriate parser for a file based on extension."""
        ext = file_path.rsplit(".", 1)[-1] if "." in file_path else ""
        parser = self._by_extension.get(f".{ext}")
        return parser

    def get_parser(self, language_name: str) -> Optional[ParserInterface]:
        """Get a parser by its registered language name."""
        return self._parsers.get(language_name)

    def list_languages(self) -> Dict[str, Dict]:
        """List all registered languages with their capabilities."""
        return {
            name: {
                "name": p.name,
                "extensions": p.extensions,
                "capability": p.capability,
            }
            for name, p in self._parsers.items()
        }

    def list_parsers(self) -> List[ParserInterface]:
        """Return all registered parser instances."""
        return list(self._parsers.values())

    def parse_file(self, file_path: str) -> Optional[ParsedFileIR]:
        """Try to parse a file, returning None if no parser handles it.

        If the parser raises, we catch and return an error entry instead of
        aborting the whole analysis.
        """
        parser = self.get_parser_for_file(file_path)
        if parser is None:
            return None

        try:
            return parser.analyze_file(file_path)
        except Exception as e:
            # Parser failure should not abort analysis
            return ParsedFileIR(
                path=file_path,
                errors=[f"Parser error: {e}"],
                unresolved=[],
            )

    def get_capability(self, language_name: str) -> str:
        """Return the capability level for a language.

        'full'   - parser fully supports the language constructs
        'partial'- parser recognises the language but only extracts a subset
        'unsupported'- language not recognised or parser not available
        """
        parser = self._parsers.get(language_name)
        if parser is None:
            return "unsupported"
        return parser.capability


# Global registry instance
_registry: ParserRegistry = ParserRegistry()


def get_registry() -> ParserRegistry:
    """Return the global parser registry (for import by other modules)."""
    return _registry


def register(parser: ParserInterface) -> None:
    """Register a parser into the global registry."""
    _registry.register(parser)


def parse_file(file_path: str) -> Optional[ParsedFileIR]:
    """Try to parse a file using the global registry."""
    return _registry.parse_file(file_path)


def list_languages() -> Dict[str, Dict]:
    """List all registered languages."""
    return _registry.list_languages()


def get_capability(language_name: str) -> str:
    """Return capability level for a language."""
    return _registry.get_capability(language_name)