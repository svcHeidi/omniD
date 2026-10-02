"""A solver repository's helper scripts: listed with a usage line, and runnable
as a workflow step.

The repository is the truth: its ``omnidriver.toml`` names the scripts folder,
the CLI puts it on the ``DriverContext`` (``scripts_dir``), and nothing here
keeps a catalogue of what the folder holds.
"""

from __future__ import annotations

import ast
import os
import re
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_SCRIPT_SUFFIXES = {".py", ".sh"}
_SKIPPED_DIRECTORIES = {"__pycache__", "tests"}
_HELP_TIMEOUT_S = 10
# A script that never mentions an option parser has no `--help` to ask for.
_PARSES_OPTIONS = re.compile(r"argparse|optparse|getopt|--help")
_DESCRIPTION_HEADING = re.compile(r"^#\s*Description\s*$")
_USAGE_TEXT = re.compile(r"""\busage:\s*(.+?)\s*(?:["'](?:\s|$)|$)""", re.IGNORECASE | re.MULTILINE)


class ScriptError(RuntimeError):
    """A script cannot be run as asked."""


def _is_script(path: Path, root: Path) -> bool:
    """A file directly in ``root`` with a script suffix or the executable bit,
    or an executable file below it (a script keeping its library next to it)."""
    if not path.is_file() or path.name.startswith("."):
        return False
    if os.access(path, os.X_OK):
        return True
    return path.parent == root and path.suffix in _SCRIPT_SUFFIXES


def find_script(name: str, driver_context: Any | None) -> Path | None:
    """The script a step command names: a path relative to the context's
    ``scripts_dir`` and inside it. ``None`` when the context supplies no folder."""
    root = getattr(driver_context, "scripts_dir", None)
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


def _help_usage(path: Path, text: str, environ: Mapping[str, str]) -> str | None:
    """The first line of ``--help``, asked only of a script that parses options."""
    if not _PARSES_OPTIONS.search(text):
        return None
    try:
        completed = subprocess.run(
            (*script_argv(path, environ), "--help"), capture_output=True, text=True,
            timeout=_HELP_TIMEOUT_S, stdin=subprocess.DEVNULL, check=False,
        )
    except (OSError, subprocess.TimeoutExpired, ScriptError):
        return None
    return _first_line(completed.stdout) if completed.returncode == 0 else None


def list_scripts(driver_context: Any, environ: Mapping[str, str]) -> list[dict[str, str | None]]:
    """Every script in the context's ``scripts_dir`` with its usage line: the
    docstring's or header's first line when the file states one, else the first
    line of ``--help`` (run under ``environ``'s ``PATH``), else ``None``. Empty
    when the context supplies no folder."""
    root = driver_context.scripts_dir
    if root is None or not root.is_dir():
        return []
    listed = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in _SKIPPED_DIRECTORIES for part in relative.parts) or not _is_script(path, root):
            continue
        text = path.read_text(errors="replace")
        listed.append({
            "name": relative.as_posix(),
            "path": str(path),
            "usage": _static_usage(path, text) or _help_usage(path, text, environ),
        })
    return listed
