"""React framework extension for the Codebase Knowledge Graph.

This extension enriches the IR when analyzing JavaScript/TypeScript projects
that use React. It identifies React-specific patterns: components, hooks,
JSX elements, and common component patterns.

Note: This is a framework enrichment extension, not a parser. It runs after
the JavaScript/TypeScript parser has extracted basic symbols and adds
React-specific context.
"""

from ir_schema import (
    ParsedFileIR,
    SymbolIR,
    ImportIR,
    FunctionIR,
    ClassIR,
    SourceLocation,
)


def enrich_with_react(ir: ParsedFileIR) -> ParsedFileIR:
    """Enrich a parsed JS/TS file's IR with React framework information.

    Looks for React patterns in the source code and adds related symbols
    and relationships to the IR.

    Args:
        ir: The unified IR from parsing a JS/TS file.

    Returns:
        The enriched IR with React-specific additions.
    """
    enriched_ir = ParsedFileIR(
        path=ir.path,
        source_code=ir.source_code,
        symbols=list(ir.symbols),
        imports=list(ir.imports),
        exports=list(ir.exports),
        functions=list(ir.functions),
        classes=list(ir.classes),
        unresolved=list(ir.unresolved),
        errors=list(ir.errors),
    )

    source = ir.source_code or ""

    # 1. Detect React component functions
    # Pattern: function ComponentName() or const ComponentName = () => 
    component_patterns = [
        r"function\s+(\w+)\s*\(",
        r"const\s+(\w+)\s*=\s*\([^)]*\)\s*=>",
        r"const\s+(\w+)\s*=\s*\(\s*\)\s*=>",
    ]

    for pattern in component_patterns:
        for match in re.finditer(pattern, source):
            comp_name = match.group(1)
            # Skip built-in HTML elements and common JS names
            if comp_name.lower() in {"div", "span", "a", "p", "h1", "h2", "h3", "input", "button", "form"}:
                continue

            existing_fn_names = {f.name for f in enriched_ir.functions}
            existing_cls_names = {c.name for c in enriched_ir.classes}

            if comp_name not in existing_fn_names and comp_name not in existing_cls_names:
                # Find line number
                line_num = 0
                lines = source.split("\n")
                for i, line in enumerate(lines):
                    if re.search(pattern, line) and match.start() < sum(len(l) + 1 for l in lines[:i]) + len(match.group(0)):
                        line_num = i
                        break

                enriched_ir.functions.append(
                    FunctionIR(
                        name=comp_name,
                        line=line_num,
                        column=0,
                        is_async=False,
                        is_generator=False,
                        decorators=[],
                        parameters=0,
                    )
                )

    # 2. Detect React hooks
    hook_pattern = re.compile(r"use(\w+)\s*\(", re.MULTILINE)
    for match in hook_pattern.finditer(source):
        hook_name = match.group(1)
        # Add as a symbol
        already_exists = any(
            s.name == hook_name for s in enriched_ir.symbols
        )
        if not already_exists:
            enriched_ir.symbols.append(
                SymbolIR(
                    name=hook_name,
                    kind="variable",
                    location=SourceLocation(
                        file=ir.path,
                        line=match.start(),
                        column=0,
                    ),
                    evidence="react_hook",
                )
            )

    # 3. Detect JSX elements (self-closing or with children)
    jsx_pattern = re.compile(r"<(\w+)[^>]*/?>", re.MULTILINE)
    jsx_element_names = []
    for match in jsx_pattern.finditer(source):
        elem = match.group(1)
        # Skip HTML elements
        if elem.lower() in {"div", "span", "a", "p", "h1", "h2", "h3", "input", "button", "form", "br", "hr", "img"}:
            continue
        if elem not in jsx_element_names:
            jsx_element_names.append(elem)

    # Add JSX element symbols
    for elem in jsx_element_names[:10]:
        already_exists = any(
            s.name == elem for s in enriched_ir.symbols
        )
        if not already_exists:
            enriched_ir.symbols.append(
                SymbolIR(
                    name=elem,
                    kind="variable",
                    location=SourceLocation(
                        file=ir.path,
                        line=0,
                        column=0,
                    ),
                    evidence="jsx_element",
                )
            )

    # 4. Detect import of React
    react_import = re.search(r"import\s+React\s+from['\"]react['\"]|from\s+['\"]react['\"].*import\s+React", source)
    if react_import:
        # Already in imports, but mark as React-aware
        pass

    # 5. Detect export of default component
    default_export = re.search(r"export\s+default\s+(\w+)", source)
    if default_export:
        comp_name = default_export.group(1)
        existing_fn_names = {f.name for f in enriched_ir.functions}
        if comp_name not in existing_fn_names:
            line_num = 0
            lines = source.split("\n")
            for i, line in enumerate(lines):
                if f"export default {comp_name}" in line or f"export default {comp_name};" in line:
                    line_num = i
                    break
            enriched_ir.functions.append(
                FunctionIR(
                    name=comp_name,
                    line=line_num,
                    column=0,
                    is_async=False,
                    is_generator=False,
                    decorators=[],
                    parameters=0,
                )
            )

    return enriched_ir


# Need to import re at the top
import re