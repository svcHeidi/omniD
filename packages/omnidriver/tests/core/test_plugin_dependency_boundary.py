from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import omnidriver.core

# omnidriver.core.__file__ = .../src/omnidriver/core/__init__.py
_CORE_ROOT = Path(omnidriver.core.__file__).resolve().parent
_PACKAGE_ROOT = _CORE_ROOT.parent  # .../src/omnidriver -- the shipped package, tests/ is a sibling of src/


def test_core_imports_cardiac_implementation_only_at_compatibility_boundary() -> None:
    offenders: list[str] = []
    for path in _CORE_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            module = ""
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if "omnidriver.cardiacfoam" in alias.name:
                        offenders.append(f"{path.relative_to(_CORE_ROOT)}:{node.lineno}")
                continue
            if "omnidriver.cardiacfoam" in module:
                offenders.append(f"{path.relative_to(_CORE_ROOT)}:{node.lineno}")

    assert offenders == []


def test_core_never_imports_an_environment_adapter() -> None:
    offenders: list[str] = []
    for path in _CORE_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("omnidriver.openfoam"):
                offenders.append(f"{path.relative_to(_CORE_ROOT)}:{node.lineno}")
            elif isinstance(node, ast.Import) and any(
                alias.name.startswith("omnidriver.openfoam") for alias in node.names
            ):
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


def test_core_executable_literals_do_not_encode_adapter_conventions() -> None:
    """Executable Core code consumes adapter conventions through capabilities."""
    forbidden = (
        "Allrun",
        "Allclean",
        "postProcessing",
        "controlDict",
        "electroProperties",
        "cardiacFoam",
        "processor*",
        "constant/",
        "system/",
        "regressionTests",
        "blockMeshDict",
        "post_processing",
    )
    offenders: list[str] = []

    def docstring_nodes(tree: ast.AST) -> set[int]:
        nodes: set[int] = set()
        for parent in ast.walk(tree):
            body = getattr(parent, "body", None)
            if not isinstance(body, list) or not body:
                continue
            first = body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                nodes.add(id(first.value))
        return nodes

    for path in _CORE_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        docs = docstring_nodes(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if id(node) in docs:
                continue
            if any(token in node.value for token in forbidden):
                offenders.append(f"{path.relative_to(_CORE_ROOT)}:{node.lineno}")

    assert offenders == []


def test_catalogue_paths_follow_adapter_case_file_rules(tmp_path: Path) -> None:
    """Dictionary discovery must not assume environment directory names."""
    from omnidriver.core.plugin_profile import CaseFileRule
    from omnidriver.core.strict_planning import _owned_dict_relpaths

    case_root = tmp_path / "case"
    (case_root / "config").mkdir(parents=True)
    (case_root / "config" / "solver.yaml").write_text("solver: demo\n")
    rules = (
        CaseFileRule(
            path="config/solver.yaml",
            kind="configuration",
            role="x-neutral.configuration",
            required="always",
        ),
    )
    context = SimpleNamespace(
        capabilities=SimpleNamespace(
            case_files=SimpleNamespace(all_rules=lambda: rules),
            override_schema=SimpleNamespace(
                dict_entry_catalog=lambda: {"solver.yaml": ()},
            ),
        ),
    )
    spec = SimpleNamespace(case_root=case_root, metadata={})

    assert _owned_dict_relpaths(spec, context) == ("config/solver.yaml",)
