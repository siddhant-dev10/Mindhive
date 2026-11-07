"""Pony Tail Skill Guardrails Engine.
Enforces the 7-Step Ladder of Laziness by Dietrich Gebert.
Audits AST imports, standard library compliance, and diff line counts.
"""

import ast
import os
import re
from pathlib import Path
from typing import List, Dict, Any, Tuple
from agenthive.config import settings

# Standard library modules whitelisted in Python 3.9/3.11
STDLIB_WHITELIST = {
    "__future__", "abc", "argparse", "array", "asyncio", "base64", "builtins", "collections", "concurrent",
    "contextlib", "copy", "csv", "dataclasses", "datetime", "decimal", "difflib",
    "enum", "errno", "fnmatch", "functools", "glob", "gzip", "hashlib", "heapq",
    "hmac", "html", "http", "importlib", "inspect", "io", "itertools", "json",
    "logging", "math", "multiprocessing", "os", "pathlib", "pickle", "platform",
    "pprint", "queue", "random", "re", "shutil", "signal", "socket", "sqlite3",
    "ssl", "stat", "string", "struct", "subprocess", "sys", "tempfile", "threading",
    "time", "traceback", "types", "typing", "unittest", "urllib", "uuid", "weakref",
    "xml", "zipfile", "zlib"
}

class PonyTailEngine:
    def __init__(self, mode: str = "full", enforce_stdlib_only: bool = True, max_diff_lines: int = 300):
        self.mode = mode
        self.enforce_stdlib_only = enforce_stdlib_only
        self.max_diff_lines = max_diff_lines

    def audit_python_file(self, file_path: str) -> Dict[str, Any]:
        """Inspects Python file AST to ensure zero unauthorized third-party dependencies."""
        path = Path(file_path)
        if not path.exists():
            return {"valid": False, "error": f"File {file_path} not found"}

        try:
            content = path.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(path))
        except Exception as e:
            return {"valid": False, "error": f"Failed to parse AST: {e}"}

        imported_modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_mod = alias.name.split(".")[0]
                    imported_modules.add(root_mod)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root_mod = node.module.split(".")[0]
                    imported_modules.add(root_mod)

        # Filter out local project package imports
        unauthorized = []
        for mod in imported_modules:
            if mod in ["src", "tests", "engine", "cli", "app"]:
                continue
            if mod not in STDLIB_WHITELIST:
                unauthorized.append(mod)

        is_valid = True
        violations = []
        if self.enforce_stdlib_only and unauthorized:
            is_valid = False
            violations.append(
                f"Pony Tail Violation: External dependencies detected: {unauthorized}. "
                f"Rule 3 mandates standard library only."
            )

        line_count = len(content.splitlines())
        if line_count > self.max_diff_lines:
            violations.append(
                f"Pony Tail Warning: File exceeds {self.max_diff_lines} lines ({line_count} LOC). "
                f"Consider pruning abstractions."
            )

        return {
            "file": str(path),
            "valid": is_valid,
            "line_count": line_count,
            "imported_modules": list(imported_modules),
            "unauthorized_modules": unauthorized,
            "violations": violations
        }

    def audit_workspace(self, workspace_dir: str) -> Dict[str, Any]:
        """Audits all python files in workspace/src and workspace/tests."""
        ws = Path(workspace_dir)
        results = []
        all_valid = True

        for py_file in ws.glob("**/*.py"):
            res = self.audit_python_file(str(py_file))
            results.append(res)
            if not res["valid"]:
                all_valid = False

        return {
            "workspace": str(ws),
            "passed": all_valid,
            "audited_files": len(results),
            "details": results
        }

ponytail_guard = PonyTailEngine(
    mode=settings.ponytail_mode,
    enforce_stdlib_only=settings.ponytail_enforce_stdlib,
    max_diff_lines=settings.ponytail_max_diff_lines,
)
