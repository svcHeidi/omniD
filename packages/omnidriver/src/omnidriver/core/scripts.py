"""A solver repository's helper scripts: listed with a usage line read from the file, never by running it.

The repository is the truth: its ``omnidriver.toml`` names the folder and nothing here keeps a catalogue.
"""

from __future__ import annotations

import ast
import os
import re
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_SCRIPT_SUFFIXES = {".py", ".sh"}
_SKIPPED_DIRECTORIES = {"__pycache__", "tests"}
NO_USAGE = "no usage line"
_DESCRIPTION_HEADING = re.compile(r"^#\s*Description\s*$")
_USAGE_TEXT = re.compile(r"""\busage:\s*(.+?)\s*(?:["'](?:\s|$)|$)""", re.IGNORECASE | re.MULTILINE)


class ScriptError(RuntimeError):
    """A script cannot be run as asked."""


def _is_script(path: Path, root: Path) -> bool:
    """A ``.py``/``.sh`` file or executable directly in ``root``, or an executable below it."""
    if not path.is_file() or path.name.startswith("."):
        return False
    if os.access(path, os.X_OK):
        return True
    return path.parent == root and path.suffix in _SCRIPT_SUFFIXES


def _scripts_folder(driver_context: Any | None) -> Path | None:
    repository = getattr(driver_context, "repository", None)
    return None if repository is None else repository.scripts


def find_script(name: str, driver_context: Any | None) -> Path | None:
    """The script a step command names: a path relative to the context's
    scripts folder and inside it. ``None`` when the context has no repository."""
    root = _scripts_folder(driver_context)
    if root is None or not name or Path(name).is_absolute():
        return None
    path = (root / name).resolve()
    if not path.is_relative_to(root) or any(part in _SKIPPED_DIRECTORIES for part in path.relative_to(root).parts):
        return None
    return path if _is_script(path, root) else None


def script_argv(script: Path, environ: Mapping[str, str]) -> tuple[str, ...]:
    """The argv that runs ``script``. A ``.py`` file runs under the ``python3``
    on the stack's own ``PATH``; any other script runs through its shebang."""
    if script.suffix != ".py":
        return (str(script),)
    python = shutil.which("python3", path=environ.get("PATH"))
    if python is None:
        raise ScriptError(f"{script} needs python3, and the stack's PATH has none")
    return (python, str(script))


def _first_line(text: str | None) -> str | None:
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()
    return None


def _static_usage(path: Path, text: str) -> str | None:
    if path.suffix == ".py":
        try:
            docstring = _first_line(ast.get_docstring(ast.parse(text)))
        except SyntaxError:
            docstring = None
        if docstring:
            return docstring
    comments = [line.strip() for line in text.splitlines() if line.startswith("#")]
    for index, line in enumerate(comments):
        if _DESCRIPTION_HEADING.match(line):
            described = _first_line("\n".join(comment.lstrip("#") for comment in comments[index + 1:]))
            if described:
                return described
    match = _USAGE_TEXT.search(text)
    return match.group(1).replace("$0", path.name) if match else None


def list_scripts(driver_context: Any) -> list[dict[str, str]]:
    """Every script ``find_script`` would return from the repository's scripts
    folder, with the first line of its docstring or header or its ``usage:``
    line, else ``NO_USAGE``. Nothing is run. Empty when the context has no
    repository."""
    root = _scripts_folder(driver_context)
    if root is None or not root.is_dir():
        return []
    listed = []
    for path in sorted(root.rglob("*")):
        name = path.relative_to(root).as_posix()
        script = find_script(name, driver_context)
        if script is not None:
            listed.append({
                "name": name, "path": str(script),
                "usage": _static_usage(script, script.read_text(errors="replace")) or NO_USAGE,
            })
    return listed
