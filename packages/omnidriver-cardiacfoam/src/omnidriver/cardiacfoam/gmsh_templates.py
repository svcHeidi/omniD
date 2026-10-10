"""A gmsh step's ``-setnumber`` names against the template it meshes."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from omnidriver.core.planning_types import StrictDiagnostic, diagnostic

_DECLARATION = re.compile(r"\b(?:DefineConstant|DefineNumber)\s*\[(.*?)\]\s*;?", re.DOTALL)
_NAME_OPTION = re.compile(r'\bName\s+"([^"]+)"')
_ASSIGNED = re.compile(r"^\s*([A-Za-z_]\w*)\s*=")
_COMMENT = re.compile(r"//[^\n]*|/\*.*?\*/", re.DOTALL)
_TEMPLATE_SUFFIXES = (".geo", ".geo.template")


def declared_numbers(template_text: str) -> frozenset[str]:
    """The names ``gmsh -setnumber`` can set in the template: each
    ``DefineConstant``/``DefineNumber`` item's ``Name "..."`` option, or its
    variable when it has none."""
    names: set[str] = set()
    for body in _DECLARATION.findall(_COMMENT.sub("", template_text)):
        for item in _top_level_items(body):
            option = _NAME_OPTION.search(item)
            assigned = _ASSIGNED.match(item)
            if option:
                names.add(option.group(1))
            elif assigned:
                names.add(assigned.group(1))
    return frozenset(names)


def _top_level_items(body: str) -> list[str]:
    items, depth, start = [], 0, 0
    for index, char in enumerate(body):
        if char in "{(":
            depth += 1
        elif char in "})":
            depth -= 1
        elif char == "," and depth == 0:
            items.append(body[start:index])
            start = index + 1
    items.append(body[start:])
    return items


def undeclared_setnumber_diagnostics(case_root: Path, workflow_dag: dict[str, Any] | None) -> tuple[StrictDiagnostic, ...]:
    """An error for each gmsh step that passes ``-setnumber <name>`` to a
    template that does not declare ``<name>``: gmsh then ignores the option,
    reports the template's own undefined value as errors, still writes a
    degenerate mesh and exits 0, and the failure surfaces a step later. A
    template that is not under ``case_root`` is not judged."""
    found: list[StrictDiagnostic] = []
    for step in (workflow_dag or {}).get("steps", ()):
        if step.get("command") != "gmsh":
            continue
        args = [str(arg) for arg in step.get("args", ())]
        names = [args[i + 1] for i, arg in enumerate(args[:-1]) if arg == "-setnumber"]
        templates = [arg for arg in args if arg.endswith(_TEMPLATE_SUFFIXES)]
        if not names or len(templates) != 1:
            continue
        path = Path(case_root) / step.get("cwd", ".") / templates[0]
        if not path.is_file():
            continue
        declared = declared_numbers(path.read_text())
        for name in dict.fromkeys(names):
            if name in declared:
                continue
            step_id = step.get("id", "gmsh")
            found.append(diagnostic(
                "error", "gmsh_setnumber_not_declared",
                f"Step {step_id!r} passes `-setnumber {name}` to {templates[0]}, which does not declare "
                f"{name!r} with DefineConstant, so gmsh ignores the option. The template declares "
                f"{', '.join(sorted(declared)) or 'nothing'}.",
                source="gmsh", field=f"workflow_dag.steps.{step_id}",
                detail={"rule": "gmsh -setnumber names a DefineConstant of the template",
                        "template": templates[0], "name": name, "declared": sorted(declared)},
            ))
    return tuple(found)
