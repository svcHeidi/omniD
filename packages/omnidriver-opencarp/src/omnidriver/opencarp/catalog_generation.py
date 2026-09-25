"""Build the catalog by asking the installed binary (evidence B1-B6, G6).

+Help lists every parameter with its type. +Help <name> gives the detail,
and needs a concrete index (``stim[0]...``, not ``stim[Int]...``; B3/B4).
Build identity comes from -buildinfo's tag and hash lines only: its
repository line embeds a CI token (A8, G3)."""
from __future__ import annotations

import re
import shutil
import subprocess
from typing import Any, Mapping

_LIST_LINE = re.compile(r"^\s+'?-(?P<name>[^' ]+)'?\s+(?P<type>.+?)\s*$")
_FIELD = re.compile(r"^\t(type|default|min|max):\s*(.*)$")
_TYPED = re.compile(r"^\((\w+)\)\((.*)\)$")
_BLOCK = re.compile(r"^\t(menu|Depends on|Changes the allocation of|Changes the default value of): \{$")
_MENU_ITEM = re.compile(r"^\t\t\((\w+)\)\((.*?)\)\t(.*)$")


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
    """A menu item as the value a .par assigns, not +Help's source spelling.

    **Added 2026-09-25 (review B-I4).** +Help prints each item as a typed C
    literal: ``(Short)(1)``, but ``(String)("ref")`` for ``ginkgo_exec``, a
    String menu, quotes included. Kept verbatim, every legal String value was
    refused ("ref" is not ``'"ref"'``) and the quoted one was then refused by
    ``format_value``, so the parameter could not be set at all. The quotes
    are the C literal's, not part of the value, so a String item drops them.
    """
    if item_type == "String" and len(spelled) >= 2 and spelled[0] == spelled[-1] == '"':
        return spelled[1:-1]
    return spelled


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
    menu = tuple(_menu_value(m[1], m[2]) for item in blocks.get("menu", []) if (m := _MENU_ITEM.match(item)))
    allocates = tuple(i.strip() for i in blocks.get("Changes the allocation of", []) if i.strip() and "[" not in i)
    return {
        "default": _typed(fields.get("default")), "minimum": _typed(fields.get("min")),
        "maximum": _typed(fields.get("max")), "menu": list(menu), "allocates": list(allocates),
        "description": " ".join(description),
    }


def build_identity(binary: str, env: Mapping[str, str] | None) -> dict[str, str]:
    identity = {}
    for line in _run(binary, ["-buildinfo"], env).splitlines():
        if line.startswith("*** GIT tag:"):
            identity["tag"] = line.split(":", 1)[1].strip()
        elif line.startswith("*** GIT hash:"):
            identity["hash"] = line.split(":", 1)[1].strip()
    if set(identity) != {"tag", "hash"}:
        raise CatalogError("-buildinfo printed no tag/hash; is DYLD_LIBRARY_PATH set? (A4-A6)")
    return identity


def build_catalog(binary: str = "openCARP", env: Mapping[str, str] | None = None) -> dict[str, Any]:
    resolved = shutil.which(binary, path=(env or {}).get("PATH")) if env else shutil.which(binary)
    if resolved is None:
        raise CatalogError(f"{binary} is not on PATH")
    parameters = []
    for name, opencarp_type in parse_help_list(_run(resolved, ["+Help"], env)):
        if opencarp_type.startswith("{"):
            # B8: a whole-array shorthand has no detail block under any
            # spelling; only its elements do. It is kept so the validator
            # can name it and ask for elements.
            detail = {"default": None, "minimum": None, "maximum": None,
                      "menu": [], "allocates": [], "description": ""}
        else:
            concrete = name.replace("[Int]", "[0]")
            detail = parse_help_detail(concrete, _run(resolved, ["+Help", concrete], env))
        parameters.append({"name": name, "type": opencarp_type, **detail})
    return {"opencarp": build_identity(resolved, env), "parameters": parameters}
