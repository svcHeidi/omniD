from __future__ import annotations

import ast
from pathlib import Path

import omnidriver.core

# omnidriver.core.__file__ = .../src/omnidriver/core/__init__.py
_CORE_ROOT = Path(omnidriver.core.__file__).resolve().parent
_PACKAGE_ROOT = _CORE_ROOT.parent  # .../src/omnidriver -- the shipped package, tests/ is a sibling of src/


def test_core_imports_cardiac_implementation_only_at_compatibility_boundary() -> None:
    offenders: list[str] = []
    for path in _CORE_ROOT.rglob("*.py"):
        if path.name == "compatibility.py":
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            module = ""
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if "omnidriver.cardiac" in alias.name:
                        offenders.append(f"{path.relative_to(_CORE_ROOT)}:{node.lineno}")
                continue
            if "omnidriver.cardiac" in module:
                offenders.append(f"{path.relative_to(_CORE_ROOT)}:{node.lineno}")

    assert offenders == []


def test_production_consumers_do_not_bypass_capability_bundle() -> None:
    offenders: list[str] = []
    for path in _PACKAGE_ROOT.rglob("*.py"):
        if "tests" in path.parts or path.name in {"plugin_interface.py", "plugin_capabilities.py"}:
            continue
        text = path.read_text()
        if "driver_context.plugin." in text:
            offenders.append(str(path.relative_to(_PACKAGE_ROOT)))
    assert offenders == []
