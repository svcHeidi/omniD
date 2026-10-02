"""Read-only inspection of the files an OpenFOAM dictionary depends on.

Separate from :func:`mutators.read_foam_entry`, which only inspects lexical
source: this follows ``#include`` directives, and never runs ``foamDictionary``.
"""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Mapping

from .mutators import _mask_comments

_EXECUTABLE_DIRECTIVE = re.compile(r"#(?:calc|codeStream|eval)\b")
_QUOTED_INCLUDE = re.compile(r'^\s*#include(?P<optional>IfPresent)?\s+"(?P<path>[^"]+)"', re.MULTILINE)
_ETC_INCLUDE = re.compile(r'^\s*#includeEtc\s+"(?P<path>[^"]+)"', re.MULTILINE)
_OTHER_INCLUDE = re.compile(r"^\s*#includeFunc\b|^\s*#include(?!Etc\s+\")(?!IfPresent\s+\")(?!\s+\")", re.MULTILINE)
_ENV_REFERENCE = re.compile(r"\$(?:\{(?P<braced>[A-Za-z_][A-Za-z0-9_]*)\}|(?P<bare>[A-Za-z_][A-Za-z0-9_]*))")


def _mask_quoted_strings(text: str) -> str:
    """Hide quoted literals while retaining offsets for directive scanning."""
    return re.sub(
        r'"(?:\\.|[^"\\])*"', lambda match: " " * len(match.group()), text,
    )


def _expand_include(value: str, environment: Mapping[str, str]) -> tuple[str | None, tuple[str, ...], str | None]:
    keys: list[str] = []

    def replace(match: re.Match[str]) -> str:
        key = match.group("braced") or match.group("bare")
        keys.append(key)
        if key not in environment:
            raise KeyError(key)
        return environment[key]

    try:
        return _ENV_REFERENCE.sub(replace, value), tuple(keys), None
    except KeyError as exc:
        return None, tuple(keys), f"include requires unset environment variable {exc.args[0]!r}"


def find_etc_file(
    name: str, environment: Mapping[str, str],
) -> tuple[Path | None, tuple[Path, ...]]:
    """Locate an ``#includeEtc`` dependency the way the native runtime does.

    Returns ``(selected, candidates)``: the first existing file in search order,
    and every location searched whether or not it exists. An absent candidate
    still matters -- a file later appearing at a higher-priority location
    changes which file the next run reads, so a plan's preconditions must
    record that those locations were empty.

    Modelled on ESI's (openfoam.com) and Foundation's (openfoam.org) own
    ``bin/foamEtcFile``/``etc/bashrc``: both build the same six-slot search
    order -- user, then group/site, then distribution, each in a versioned and
    unversioned form -- gated by a ``FOAM_CONFIG_MODE`` string whose
    *membership* of ``u``/``g``/``o`` letters, not order, selects which groups
    run; unset or unrecognised means all three. The two families disagree on
    where the site root and version default from when unset (see the ``if
    api:`` branch below) and only ESI has ``FOAM_CONFIG_MODE``/
    ``FOAM_CONFIG_ETC`` at all -- modelling them unconditionally is harmless
    for Foundation, which never sets them.
    """
    mode = environment.get("FOAM_CONFIG_MODE") or ""
    if not mode or mode[0] not in "ugo":
        mode = "ugo"  # unset or unrecognised: both scripts search all three groups

    api = environment.get("FOAM_API")
    version = api if api else environment.get("WM_PROJECT_VERSION", "")
    candidates: list[Path] = []

    if "u" in mode:
        home = environment.get("HOME")
        if home:
            if version:
                candidates.append(Path(home) / ".OpenFOAM" / version / name)
            candidates.append(Path(home) / ".OpenFOAM" / name)

    if "g" in mode:
        site = environment.get("WM_PROJECT_SITE")
        if not site:
            if api:
                # ESI's groupDir defaults from the project dir itself (etc/bashrc).
                project_dir = environment.get("WM_PROJECT_DIR")
                if project_dir:
                    site = str(Path(project_dir) / "site")
            else:
                # Foundation's siteDir defaults from the project dir's *parent*,
                # exported as WM_PROJECT_INST_DIR by its own etc/bashrc.
                inst_dir = environment.get("WM_PROJECT_INST_DIR")
                if inst_dir:
                    site = str(Path(inst_dir) / "site")
        if site:
            if version:
                candidates.append(Path(site) / version / "etc" / name)
            candidates.append(Path(site) / "etc" / name)

    if "o" in mode:
        config_etc = environment.get("FOAM_CONFIG_ETC")
        if config_etc:
            candidates.append(Path(config_etc) / name)
        project_dir = environment.get("WM_PROJECT_DIR")
        if project_dir:
            candidates.append(Path(project_dir) / "etc" / name)
        else:
            # FOAM_ETC stands in for WM_PROJECT_DIR/etc when only it is set
            # neither published script reads FOAM_ETC itself, but it is
            # normally exported equal to that path.
            etc_root = environment.get("FOAM_ETC")
            if etc_root:
                candidates.append(Path(etc_root) / name)

    resolved = tuple(dict.fromkeys(candidates))
    for candidate in resolved:
        if candidate.is_file():
            return candidate, resolved
    return None, resolved


def _inspect_source_closure(
    path: Path, environment: Mapping[str, str],
) -> tuple[tuple[Path, ...], tuple[Path, ...], tuple[str, ...], str | None]:
    """Return safe local includes, or the explicit reason resolution is gated."""
    pending = [path.resolve()]
    inspected: list[Path] = []
    absent_optional: list[Path] = []
    seen: set[Path] = set()
    environment_keys: set[str] = set()
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        try:
            text = current.read_text()
        except OSError as exc:
            return tuple(inspected), tuple(absent_optional), tuple(sorted(environment_keys)), f"cannot inspect dictionary dependency {current}: {exc}"
        inspected.append(current)
        try:
            lexical_text = _mask_comments(text)
        except ValueError as exc:
            return tuple(inspected), tuple(absent_optional), tuple(sorted(environment_keys)), (
                f"cannot lexically inspect dictionary dependency {current}: {exc}"
            )
        if _EXECUTABLE_DIRECTIVE.search(_mask_quoted_strings(lexical_text)):
            return tuple(inspected), tuple(absent_optional), tuple(sorted(environment_keys)), (
                f"executable dictionary directive found in {current}; "
                "pass allow_executable_directives=True to request execution"
            )
        if _OTHER_INCLUDE.search(lexical_text):
            return tuple(inspected), tuple(absent_optional), tuple(sorted(environment_keys)), (
                f"runtime-dependent include found in {current}; "
                "effective resolution is unresolved without its explicit dependency closure"
            )
        for match in _ETC_INCLUDE.finditer(lexical_text):
            environment_keys.add("FOAM_ETC")
            # Every key find_etc_file reads is recorded unconditionally, not only
            # the ones this install happens to set: recording an unused key is
            # harmless, but an unrecorded one would silently invalidate a
            # precondition (see find_etc_file's docstring for the two families).
            environment_keys.update(
                ("FOAM_API", "FOAM_CONFIG_ETC", "FOAM_CONFIG_MODE", "HOME",
                 "WM_PROJECT_VERSION", "WM_PROJECT_SITE", "WM_PROJECT_DIR",
                 "WM_PROJECT_INST_DIR")
            )
            include_name = match.group("path")
            expanded, keys, error = _expand_include(include_name, environment)
            environment_keys.update(keys)
            if error is not None:
                return tuple(inspected), tuple(absent_optional), tuple(sorted(environment_keys)), error
            assert expanded is not None
            selected, candidates = find_etc_file(expanded, environment)
            if selected is None:
                searched = ", ".join(str(candidate) for candidate in candidates) or "<no location configured>"
                return tuple(inspected), tuple(absent_optional), tuple(sorted(environment_keys)), (
                    f"#includeEtc dependency is missing: {expanded}; searched {searched}"
                )
            # Higher-priority locations that are empty today are recorded as
            # absent: a file appearing at one of them changes which file the
            # next run reads, which is a precondition, not a detail.
            for candidate in candidates:
                if candidate == selected:
                    break
                absent_optional.append(candidate)
            pending.append(selected.resolve())
        for match in _QUOTED_INCLUDE.finditer(lexical_text):
            include_name = match.group("path")
            expanded, keys, error = _expand_include(include_name, environment)
            environment_keys.update(keys)
            if error is not None:
                return tuple(inspected), tuple(absent_optional), tuple(sorted(environment_keys)), error
            assert expanded is not None
            candidate = Path(expanded)
            if not candidate.is_absolute():
                candidate = current.parent / candidate
            candidate = candidate.resolve()
            if not candidate.is_file():
                if match.group("optional"):
                    absent_optional.append(candidate)
                    continue
                return tuple(inspected), tuple(absent_optional), tuple(sorted(environment_keys)), f"local include is missing: {candidate}"
            pending.append(candidate)
    return tuple(inspected), tuple(absent_optional), tuple(sorted(environment_keys)), None


def inspect_effective_foam_configuration(
    case_root: str | Path,
    dictionary_relpaths: tuple[str, ...],
    *,
    env: Mapping[str, str] | None = None,
) -> tuple[dict[str, object], ...]:
    """Read the safe source closure of each declared OpenFOAM dictionary.

    This is intentionally inspection, not evaluation: planning must not run
    ``#codeStream`` or arbitrary directives merely to discover dependencies.
    It gives core a uniform, read-only dependency contract.
    """
    root = Path(case_root).resolve()
    environment = dict(os.environ) if env is None else dict(env)
    evaluator = shutil.which("foamDictionary", path=environment.get("PATH", ""))
    evidence: list[dict[str, object]] = []
    for relpath in sorted(set(dictionary_relpaths)):
        dictionary = root / relpath
        if not dictionary.is_file():
            continue
        inspected, absent_optional, environment_keys, message = _inspect_source_closure(
            dictionary, environment,
        )
        evidence.append({
            "dictionary": relpath,
            "status": "inspected" if message is None else "unresolved",
            "parser": "openfoam_source_closure",
            "evaluator": {
                "name": "foamDictionary",
                "path": evaluator,
            },
            "message": message,
            "inspected_files": [str(item) for item in inspected],
            "absent_optional_files": [str(item) for item in absent_optional],
            "environment_keys": list(environment_keys),
        })
    return tuple(evidence)
