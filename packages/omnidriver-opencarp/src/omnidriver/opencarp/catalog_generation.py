"""Build the catalog by asking the installed binary.

+Help lists every parameter with its type; +Help <name> gives the detail and needs a concrete index (``stim[0]...``, not ``stim[Int]...``). Build identity comes from -buildinfo's tag and hash lines only, since its repository line embeds a CI token."""
from __future__ import annotations

import re
import shutil
import subprocess
from typing import Any, Mapping

_LIST_LINE = re.compile(r"^\s+'?-(?P<name>[^' ]+)'?\s+(?P<type>.+?)\s*$")
_FIELD = re.compile(r"^\t(type|default|min|max|units):\s*(.*)$")
_TYPED = re.compile(r"^\((\w+)\)\((.*)\)$")
_BLOCK = re.compile(r"^\t(menu|Depends on|Changes the allocation of|Changes the default value of): \{$")
_MENU_ITEM = re.compile(r"^\t\t\((\w+)\)\((.*?)\)\t(.*)$")
#: openCARP's C spellings of a Flag literal; ``TO_STRING(x)`` is its string literal ``"x"``.
_FLAG_LITERALS = {"PrMTRUE": "1", "PrMFALSE": "0"}
_TO_STRING = re.compile(r"TO_STRING\((\w*)\)")
_LITERAL = re.compile(r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?|"[^"]*"')
#: +Help's spellings of a unit core's unit table names otherwise; every other unit is kept as printed.
_UNIT_SPELLINGS = {"micrometers": "um", "microseconds": "us"}


class CatalogError(RuntimeError):
    pass


def _run(binary: str, args: list[str], env: Mapping[str, str] | None) -> str:
    proc = subprocess.run([binary, *args], capture_output=True, text=True, env=dict(env) if env else None)
    return proc.stdout + proc.stderr


def parse_help_list(text: str) -> list[tuple[str, str]]:
    lines = text.splitlines()
    try:
        start = lines.index("Parameters:") + 1
    except ValueError as exc:
        raise CatalogError("+Help printed no 'Parameters:' section") from exc
    out = []
    for line in lines[start:]:
        match = _LIST_LINE.match(line)
        if match:
            out.append((match["name"], match["type"].strip("'")))
    return out


def _typed(value: str | None) -> str | None:
    if value is None:
        return None
    match = _TYPED.match(value)
    return match[2] if match else value


def _menu_value(item_type: str, spelled: str) -> str:
    # +Help prints a String item as a C literal, (String)("ref"); a .par assigns ref.
    if item_type == "String" and len(spelled) >= 2 and spelled[0] == spelled[-1] == '"':
        return spelled[1:-1]
    return spelled


def _default(spelled: str | None) -> tuple[str | None, str | None]:
    """``(default, default_expression)``: a literal as a .par spells it, else the C expression +Help printed."""
    if spelled is None:
        return None, None
    spelled = _FLAG_LITERALS.get(spelled, spelled)
    if (match := _TO_STRING.fullmatch(spelled)):
        spelled = f'"{match[1]}"'
    return (spelled, None) if _LITERAL.fullmatch(spelled) else (None, spelled)


def parse_help_detail(concrete: str, text: str) -> dict[str, Any]:
    lines = text.splitlines()
    try:
        start = lines.index(f"{concrete}:")
    except ValueError as exc:
        raise CatalogError(f"+Help {concrete} printed no detail block") from exc
    description: list[str] = []
    fields: dict[str, str] = {}
    blocks: dict[str, list[str]] = {}
    block = None
    for line in lines[start + 1:]:
        if block is not None:
            if line == "\t}":
                block = None
            else:
                blocks[block].append(line)
            continue
        if (m := _BLOCK.match(line)):
            block = m[1]
            blocks[block] = []
        elif (m := _FIELD.match(line)):
            fields[m[1]] = m[2].strip()
        elif not fields and line.strip():
            description.append(line.strip())
    items = [(_menu_value(m[1], m[2]), m[3].strip()) for item in blocks.get("menu", []) if (m := _MENU_ITEM.match(item))]
    allocates = tuple(i.strip() for i in blocks.get("Changes the allocation of", []) if i.strip() and "[" not in i)
    default, default_expression = _default(_typed(fields.get("default")))
    units = fields.get("units")
    return {
        "default": default, "default_expression": default_expression, "minimum": _typed(fields.get("min")),
        "maximum": _typed(fields.get("max")), "units": _UNIT_SPELLINGS.get(units, units), "units_as_printed": units,
        "menu": [value for value, _ in items], "menu_labels": {value: label for value, label in items},
        "allocates": list(allocates), "description": " ".join(description),
    }


def build_identity(binary: str, env: Mapping[str, str] | None) -> dict[str, str]:
    from .environment import buildinfo_identity

    identity = buildinfo_identity(_run(binary, ["-buildinfo"], env))
    if identity is None or None in identity.values():
        raise CatalogError("-buildinfo printed no tag/hash; is DYLD_LIBRARY_PATH set?")
    return {"tag": identity["tag"], "hash": identity["commit"]}


def build_catalog(binary: str = "openCARP", env: Mapping[str, str] | None = None) -> dict[str, Any]:
    resolved = shutil.which(binary, path=(env or {}).get("PATH")) if env else shutil.which(binary)
    if resolved is None:
        raise CatalogError(f"{binary} is not on PATH")
    parameters = []
    for name, opencarp_type in parse_help_list(_run(resolved, ["+Help"], env)):
        if opencarp_type.startswith("{"):
            # A whole-array shorthand has no detail block under any spelling;
            # only its elements do. It is kept so the validator can name it
            # and ask for elements.
            detail = {"default": None, "default_expression": None, "minimum": None, "maximum": None,
                      "units": None, "units_as_printed": None, "menu": [], "menu_labels": {}, "allocates": [],
                      "description": ""}
        else:
            concrete = name.replace("[Int]", "[0]")
            detail = parse_help_detail(concrete, _run(resolved, ["+Help", concrete], env))
        parameters.append({"name": name, "type": opencarp_type, **detail})
    return {"opencarp": build_identity(resolved, env), "parameters": parameters}
