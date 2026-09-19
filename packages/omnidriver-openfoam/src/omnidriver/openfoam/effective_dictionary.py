"""Explicit native effective-dictionary inspection for OpenFOAM.

This is deliberately separate from :func:`mutators.read_foam_entry`, which
only inspects lexical source.  ``foamDictionary`` can resolve includes and
substitutions, but may also execute dictionary directives; callers must opt in
to that capability rather than receiving it as an incidental parsing effect.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .mutators import _mask_comments
from .openfoam_environment import discover_openfoam_bashrc

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


class _Unset:
    """Marks ``bashrc`` as unspecified, so a default can be discovered lazily
    instead of a fixed path being invented for every machine."""

    def __repr__(self) -> str:
        return "<discover ambient OpenFOAM installation>"


_UNSET = _Unset()


@dataclass(frozen=True)
class EffectiveDictionaryResult:
    """A native effective-resolution result without overclaiming coverage."""

    status: str
    value: str | None
    parser: str
    runtime: str | None
    message: str | None = None
    inspected_files: tuple[str, ...] = ()
    absent_optional_files: tuple[str, ...] = ()
    environment_keys: tuple[str, ...] = ()


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
            etc_root = environment.get("FOAM_ETC")
            if not etc_root:
                return tuple(inspected), tuple(absent_optional), tuple(sorted(environment_keys)), (
                    "#includeEtc requires unset environment variable 'FOAM_ETC'"
                )
            include_name = match.group("path")
            expanded, keys, error = _expand_include(include_name, environment)
            environment_keys.update(keys)
            if error is not None:
                return tuple(inspected), tuple(absent_optional), tuple(sorted(environment_keys)), error
            assert expanded is not None
            candidate = (Path(etc_root) / expanded).resolve()
            if not candidate.is_file():
                return tuple(inspected), tuple(absent_optional), tuple(sorted(environment_keys)), (
                    f"#includeEtc dependency is missing: {candidate}"
                )
            pending.append(candidate)
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


def resolve_effective_foam_entry(
    path: str | Path,
    entry: str,
    *,
    bashrc: str | Path | None | _Unset = _UNSET,
    allow_executable_directives: bool = False,
    env: Mapping[str, str] | None = None,
    timeout_s: float = 10.0,
) -> EffectiveDictionaryResult:
    """Resolve one entry through native ``foamDictionary`` explicitly.

    The supported profile is an ambient OpenFOAM installation, discovered via
    :func:`discover_openfoam_bashrc` unless the caller supplies ``bashrc``
    explicitly. Passing ``bashrc=None`` explicitly opts out of bashrc sourcing
    entirely and resolves ``foamDictionary`` from ``PATH`` instead. Simple
    quoted local includes are inspected recursively before execution.
    Runtime-dependent include forms always return explicit unresolved status.
    Executable directives return ``execution_required`` unless the caller opts
    into that capability. Even with that opt-in, dependency closure remains a
    runtime concern and is reported only by the native command's outcome.
    """
    dictionary = Path(path)
    if bashrc is _UNSET:
        bashrc = discover_openfoam_bashrc()
    runtime = Path(bashrc) if bashrc is not None else None
    if not dictionary.is_file():
        return EffectiveDictionaryResult(
            status="unresolved", value=None, parser="foamDictionary",
            runtime=str(runtime) if runtime is not None else None,
            message=f"dictionary does not exist: {dictionary}",
        )
    if runtime is not None and not runtime.is_file():
        return EffectiveDictionaryResult(
            status="runtime_unavailable", value=None, parser="foamDictionary",
            runtime=str(runtime), message=f"OpenFOAM bashrc does not exist: {runtime}",
        )
    source_environment = dict(os.environ) if env is None else dict(env)
    if runtime is not None:
        # Supported OpenFOAM layouts place ``bashrc`` directly in the etc
        # directory it exports as FOAM_ETC. Resolution inspects dependencies
        # before starting the native process, so make that selected-runtime
        # fact available to the inert closure walk as well.
        source_environment.setdefault("FOAM_ETC", str(runtime.parent))
    runtime_label = (
        str(runtime) if runtime is not None
        else source_environment.get("WM_PROJECT_DIR")
    )
    inspected, absent_optional, environment_keys, gate_error = _inspect_source_closure(
        dictionary, source_environment,
    )
    if gate_error is not None:
        status = "execution_required" if "executable dictionary directive" in gate_error else "unresolved"
        if status != "execution_required" or not allow_executable_directives:
            return EffectiveDictionaryResult(
                status=status, value=None, parser="foamDictionary", runtime=runtime_label,
                message=gate_error, inspected_files=tuple(str(item) for item in inspected),
                absent_optional_files=tuple(str(item) for item in absent_optional),
                environment_keys=environment_keys,
            )
    if runtime is None:
        executable = shutil.which("foamDictionary", path=source_environment.get("PATH", ""))
        if executable is None:
            return EffectiveDictionaryResult(
                status="runtime_unavailable", value=None, parser="foamDictionary",
                runtime=source_environment.get("WM_PROJECT_DIR"),
                message="foamDictionary is not available in the execution environment",
                inspected_files=tuple(str(item) for item in inspected),
                absent_optional_files=tuple(str(item) for item in absent_optional),
                environment_keys=environment_keys,
            )
        command = (executable, str(dictionary), "-entry", entry, "-value")
        command_env = source_environment
    else:
        script = 'source "$OMNIDRIVER_FOAM_BASHRC" >/dev/null && foamDictionary "$OMNIDRIVER_DICT" -entry "$OMNIDRIVER_ENTRY" -value'
        command = ("bash", "-lc", script)
        command_env = {
            **source_environment,
            "OMNIDRIVER_FOAM_BASHRC": str(runtime),
            "OMNIDRIVER_DICT": str(dictionary),
            "OMNIDRIVER_ENTRY": entry,
        }
    try:
        completed = subprocess.run(
            command, env=command_env, text=True,
            capture_output=True, timeout=timeout_s, check=False,
        )
    except subprocess.TimeoutExpired:
        return EffectiveDictionaryResult(
            status="unresolved", value=None, parser="foamDictionary", runtime=runtime_label,
            message=f"foamDictionary timed out after {timeout_s:g} seconds",
            inspected_files=tuple(str(item) for item in inspected),
            absent_optional_files=tuple(str(item) for item in absent_optional),
            environment_keys=environment_keys,
        )
    except OSError as exc:
        return EffectiveDictionaryResult(
            status="runtime_unavailable", value=None, parser="foamDictionary", runtime=runtime_label,
            message=str(exc), inspected_files=tuple(str(item) for item in inspected),
            absent_optional_files=tuple(str(item) for item in absent_optional),
            environment_keys=environment_keys,
        )
    if completed.returncode != 0:
        return EffectiveDictionaryResult(
            status="unresolved", value=None, parser="foamDictionary", runtime=runtime_label,
            message=completed.stderr.strip() or f"foamDictionary exited with {completed.returncode}",
            inspected_files=tuple(str(item) for item in inspected),
            absent_optional_files=tuple(str(item) for item in absent_optional),
            environment_keys=environment_keys,
        )
    return EffectiveDictionaryResult(
        status="resolved", value=completed.stdout.strip(), parser="foamDictionary",
        runtime=runtime_label, inspected_files=tuple(str(item) for item in inspected),
        absent_optional_files=tuple(str(item) for item in absent_optional),
        environment_keys=environment_keys,
    )


def inspect_effective_foam_configuration(
    case_root: str | Path,
    dictionary_relpaths: tuple[str, ...],
    *,
    env: Mapping[str, str] | None = None,
) -> tuple[dict[str, object], ...]:
    """Read the safe source closure of each declared OpenFOAM dictionary.

    This is intentionally inspection, not evaluation: planning must not run
    ``#codeStream`` or arbitrary directives merely to discover dependencies.
    It gives core a uniform, read-only dependency contract; native entry
    evaluation remains the explicit apply-time operation.
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
