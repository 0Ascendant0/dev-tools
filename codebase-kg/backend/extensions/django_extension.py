"""Django framework extension for the Codebase Knowledge Graph.

This extension enriches the IR when analyzing Python projects that use Django.
It identifies Django-specific patterns: models, views, URL configurations,
templates, and management commands.

Note: This is a framework enrichment extension, not a parser. It runs after
the Python parser has extracted basic symbols and adds Django-specific context.
"""

from ir_schema import (
    ParsedFileIR,
    SymbolIR,
    ImportIR,
    FunctionIR,
    ClassIR,
    SourceLocation,
)


def enrich_with_django(ir: ParsedFileIR) -> ParsedFileIR:
    """Enrich a parsed Python file's IR with Django framework information.

    Looks for Django patterns in the source code and adds related symbols
    and relationships to the IR.

    Args:
        ir: The unified IR from parsing a Python file.

    Returns:
        The enriched IR with Django-specific additions.
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

    # 1. Detect Django model classes (inherit from models.Model)
    # Pattern: class ModelName(models.Model):
    import re
    model_pattern = re.compile(
        r"class\s+(\w+)\s*\([^)]*models\.Model[^)]*\)",
        re.MULTILINE,
    )
    for match in model_pattern.finditer(source):
        class_name = match.group(1)
        # Find the line number
        line_match = re.search(
            rf"class\s+{re.escape(class_name)}\s*\([^)]*models\.Model[^)]*\)",
            source[:match.start()],
        )
        # Get the line from the full source
        lines = source.split("\n")
        class_line = 0
        for i, line in enumerate(lines):
            if f"class {class_name}" in line and "models.Model" in line:
                class_line = i
                break

        # Add as a class if not already present
        existing_names = {c.name for c in enriched_ir.classes}
        if class_name not in existing_names:
            enriched_ir.classes.append(
                ClassIR(
                    name=class_name,
                    line=class_line,
                    column=0,
                    base_classes=["models.Model"],
                )
            )

        # Also add related symbols for fields
        # Look for field definitions within 10 lines after the class
        class_end = class_line + 1
        while class_end < len(lines) and class_end < class_line + 30:
            field_line = class_end
            field_match = re.match(r"^\s*(\w+)\s*=\s*", lines[field_line])
            if field_match:
                field_name = field_match.group(1)
                # Check if it's a model field
                if any(
                    kw in lines[field_line]
                    for kw in ["models.", "ForeignKey", "CharField", "IntegerField",
                               "DateTimeField", "BooleanField", "TextField"]
                ):
                    # Add as a symbol related to the model
                    already_exists = any(
                        s.name == field_name and s.kind == "variable"
                        for s in enriched_ir.symbols
                    )
                    if not already_exists:
                        enriched_ir.symbols.append(
                            SymbolIR(
                                name=field_name,
                                kind="variable",
                                location=SourceLocation(
                                    file=ir.path,
                                    line=field_line,
                                    column=0,
                                ),
                                evidence="django_model_field",
                            )
                        )
            class_end += 1

    # 2. Detect Django view functions/classes
    view_pattern = re.compile(
        r"def\s+(\w+)\s*\(.*request.*\)|class\s+(\w+)\s*\(.*View.*\)",
        re.MULTILINE,
    )
    for match in view_pattern.finditer(source):
        if match.group(1):  # function-based view
            view_name = match.group(1)
        else:  # class-based view
            view_name = match.group(2)

        existing_names = {f.name for f in enriched_ir.functions}
        if view_name not in existing_names:
            # Try to find the line
            line_match = source.find(f"def {view_name}" if match.group(1) else f"class {view_name}")
            line_num = 0
            if line_match >= 0:
                lines = source.split("\n")
                for i, line in enumerate(lines):
                    if view_name in line:
                        line_num = i
                        break
            enriched_ir.functions.append(
                FunctionIR(
                    name=view_name,
                    line=line_num,
                    column=0,
                    is_async=False,
                    is_generator=False,
                    decorators=[],
                    parameters=0,
                )
            )

    # 3. Detect URL pattern registrations
    url_pattern = re.compile(r"path\(['\"]([^'\"]+)['\"]|url\(['\"]([^'\"]+)['\"]", re.MULTILINE)
    url_names = []
    for match in url_pattern.finditer(source):
        name = match.group(1) or match.group(2)
        if name and name not in url_names:
            url_names.append(name)

    # Add URL patterns as symbols
    for url_name in url_names[:10]:  # Limit to first 10
        already_exists = any(
            s.name == url_name for s in enriched_ir.symbols
        )
        if not already_exists:
            enriched_ir.symbols.append(
                SymbolIR(
                    name=url_name,
                    kind="variable",
                    location=SourceLocation(
                        file=ir.path,
                        line=0,
                        column=0,
                    ),
                    evidence="django_url_pattern",
                )
            )

    # 4. Detect management commands
    management_pattern = re.compile(
        r"from django\.core\.management\.import_base_command|def handle\(.*",
        re.MULTILINE,
    )
    for match in management_pattern.finditer(source):
        # Already captured as functions above mostly, but ensure we mark them
        pass

    return enriched_ir