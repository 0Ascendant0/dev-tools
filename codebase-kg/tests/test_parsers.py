"""Tests for the Python and JavaScript source analysers."""

from parsers.python_parser import PythonAnalyzer
from parsers.javascript_parser import JavaScriptAnalyzer


def write(tmp_path, name, content):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return str(path)


def test_python_parser_extracts_symbols_and_imports(tmp_path):
    path = write(
        tmp_path,
        "module.py",
        "\n".join(
            [
                "import os",
                "import local_module",
                "from helpers import util",
                "",
                "class Service:",
                "    def run(self):",
                "        return 1",
                "",
                "def top_level():",
                "    pass",
                "",
                "@app.route('/')",
                "def endpoint():",
                "    pass",
            ]
        ),
    )
    (tmp_path / "local_module.py").write_text("", encoding="utf-8")
    (tmp_path / "helpers").mkdir()
    (tmp_path / "helpers" / "__init__.py").write_text("", encoding="utf-8")

    result = PythonAnalyzer(str(tmp_path)).analyze_file(path)

    modules = {imp["module"] for imp in result["imports"]}
    assert "os" in modules
    assert "local_module" in modules

    functions = {fn["name"] for fn in result["functions"]}
    assert {"run", "top_level", "endpoint"} <= functions

    classes = {cls["name"] for cls in result["classes"]}
    assert classes == {"Service"}


def test_python_parser_handles_syntax_errors(tmp_path):
    path = write(tmp_path, "broken.py", "def nope(:\n")
    result = PythonAnalyzer(str(tmp_path)).analyze_file(path)
    assert result["imports"] == []
    assert result["functions"] == []


def test_js_parser_handles_esm_imports_and_arrow_functions(tmp_path):
    path = write(
        tmp_path,
        "app.js",
        "\n".join(
            [
                'import React from "react";',
                'import Button, { Secondary } from "./Button";',
                'import * as utils from "../utils/math";',
                'import "./styles.css";',
                "",
                "export const add = (a, b) => a + b;",
                "export function render() {}",
                "const helper = function () {};",
                "export default class App {}",
            ]
        ),
    )
    result = JavaScriptAnalyzer(str(tmp_path)).analyze_file(path)

    modules = {imp["module"]: imp["is_local"] for imp in result["imports"]}
    assert modules["react"] is False
    assert modules["./Button"] is True
    assert modules["../utils/math"] is True
    assert modules["./styles.css"] is True

    functions = {fn["name"] for fn in result["functions"]}
    assert {"add", "render", "helper"} <= functions

    classes = {cls["name"] for cls in result["classes"]}
    assert classes == {"App"}


def test_js_parser_ignores_comments(tmp_path):
    path = write(
        tmp_path,
        "commented.js",
        "\n".join(
            [
                '// import Ghost from "./ghost";',
                "/* import Phantom from './phantom'; */",
                "export const real = () => 1;",
            ]
        ),
    )
    result = JavaScriptAnalyzer(str(tmp_path)).analyze_file(path)

    assert result["imports"] == []
    assert [fn["name"] for fn in result["functions"]] == ["real"]


def test_js_parser_handles_commonjs(tmp_path):
    path = write(
        tmp_path,
        "legacy.cjs",
        "\n".join(
            [
                'const fs = require("fs");',
                'const local = require("./local");',
                "function load() {}",
                "module.exports = { load };",
            ]
        ),
    )
    result = JavaScriptAnalyzer(str(tmp_path)).analyze_file(path)

    modules = {imp["module"]: imp["is_local"] for imp in result["imports"]}
    assert modules["fs"] is False
    assert modules["./local"] is True
    assert "load" in {fn["name"] for fn in result["functions"]}
    assert any(exp["type"] == "module_exports" for exp in result["exports"])