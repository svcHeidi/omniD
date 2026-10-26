"""A utility's manifest compared with the C++ that declares its command line.

Each utility is found by the ``Make/files`` whose ``EXE`` rule builds it, in a supplied repository; nothing is searched
for beyond it. Three literal forms are read: ``argList::addOption``/``addBoolOption``, ``args.getOrDefault<T>`` and
``argList::addArgument``/``validArgs.append``. What they disagree on is reported like the dictionary scan, and never
fails a plan.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .build_products import _EXE_RULE, _walk
from .dict_keys_scanner import _close, _default_value, _literal, _split_args, _strip_comments

_OPTION = re.compile(r"\bargList\s*::\s*add(?P<bool>Bool)?Option\s*\(")
_ARGUMENT = re.compile(r"\bargList\s*::\s*(?:addArgument\s*\(|validArgs\s*\.\s*append\s*\()")
_DEFAULT = re.compile(r"\bargs\s*\.\s*getOrDefault\s*<[^;()]*?>\s*\(")
_INCLUDE = re.compile(r'^[ \t]*#[ \t]*include[ \t]*"([^"]+)"', re.MULTILINE)
_SOURCE_LINE = re.compile(r"^\s*([^\s=#]+\.C)\s*$", re.MULTILINE)
_SOURCE_SUFFIXES = (".C", ".H")

#: Options an OpenFOAM header or call adds to a utility's command line. They satisfy a manifest flag, and are standard
#: OpenFOAM, so a manifest need not list them.
_STANDARD_OPTIONS = {
    "addRegionOption.H": ("region",),
    "addAllRegionsOption.H": ("allRegions",),
    "addDictOption.H": ("dict",),
    "addOverwriteOption.H": ("overwrite",),
    "timeSelector::addOptions": ("time", "latestTime", "noZero", "constant", "noConstant", "withZero"),
}


@dataclass(frozen=True)
class UtilityCommandLine:
    """What a utility's C++ declares: each option with where, each ``args.getOrDefault`` default, its positional
    arguments in order, and the standard options its headers add."""

    name: str
    options: dict[str, str] = field(default_factory=dict)
    defaults: dict[str, tuple[str, str]] = field(default_factory=dict)
    arguments: tuple[str, ...] = ()
    standard: frozenset[str] = frozenset()


def utility_sources(repository_root: Path) -> dict[str, tuple[Path, ...]]:
    """Each utility a ``Make/files`` under ``repository_root`` builds into an application folder, with the C++ files it
    compiles (the ``Make/files`` lines) and the headers and sources beside that ``Make``."""
    found: dict[str, tuple[Path, ...]] = {}
    for make_files in (path for path in _walk(Path(repository_root)) if path.name == "files" and path.parent.name == "Make"):
        text = make_files.read_text(errors="replace")
        names = _EXE_RULE.findall(text)
        if not names:
            continue
        folder = make_files.parent.parent
        listed = [(folder / line).resolve() for line in _SOURCE_LINE.findall(text)]
        beside = sorted(path for path in folder.iterdir() if path.suffix in _SOURCE_SUFFIXES)
        sources = tuple(dict.fromkeys(path for path in (*listed, *beside) if path.is_file()))
        for name in names:
            found.setdefault(name, sources)
    return found


def _first_literal(text: str, open_at: int) -> tuple[list[str], int]:
    close = _close(text, open_at)
    return _split_args(text[open_at + 1:close]), close


def read_command_line(name: str, sources: Iterable[Path], *, root: Path) -> UtilityCommandLine:
    """``name``'s command line as its ``sources`` declare it; a ``source`` is named relative to ``root``."""
    options: dict[str, str] = {}
    defaults: dict[str, tuple[str, str]] = {}
    arguments: list[str] = []
    standard: set[str] = set()
    for path in sources:
        raw = path.read_text(errors="replace")
        for header in _INCLUDE.findall(raw):
            standard.update(_STANDARD_OPTIONS.get(Path(header).name, ()))
        text = _strip_comments(raw)
        if re.search(r"\btimeSelector\s*::\s*addOptions\s*\(", text):
            standard.update(_STANDARD_OPTIONS["timeSelector::addOptions"])
        where = path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)

        def at(position: int) -> str:
            return f"{where}:{text.count(chr(10), 0, position) + 1}"

        for match in _OPTION.finditer(text):
            args, _ = _first_literal(text, match.end() - 1)
            option = _literal(args[0]) if args else None
            if option is not None:
                options.setdefault(option, at(match.start()))
        for match in _ARGUMENT.finditer(text):
            args, _ = _first_literal(text, match.end() - 1)
            argument = _literal(args[0]) if args else None
            if argument is not None:
                arguments.append(argument)
        for match in _DEFAULT.finditer(text):
            args, _ = _first_literal(text, match.end() - 1)
            option = _literal(args[0]) if args else None
            if option is not None and len(args) == 2:
                defaults.setdefault(option, (args[1], at(match.start())))
    return UtilityCommandLine(
        name=name, options=options, defaults=defaults, arguments=tuple(arguments), standard=frozenset(standard),
    )


def compare_manifest(manifest: Any, command_line: UtilityCommandLine) -> list[dict[str, Any]]:
    """The manifest against what the C++ declares: an option it lacks (``uncatalogued``), a flag the C++ never declares
    (``unread``), and a default or positional count the two state differently (``disagreement``)."""
    flags = {flag.name.lstrip("-"): flag for flag in manifest.flags}
    declared = set(command_line.options) | command_line.standard
    found: list[dict[str, Any]] = []
    for option, where in sorted(command_line.options.items()):
        if option not in flags:
            found.append({"kind": "uncatalogued", "flag": f"-{option}", "source": where})
    for option in sorted(set(flags) - declared):
        found.append({"kind": "unread", "flag": f"-{option}", "note": "the manifest lists it; the C++ declares no such option"})
    for option, (text, where) in sorted(command_line.defaults.items()):
        flag = flags.get(option)
        scanned = _default_value(text, cxx=True)
        # An empty word is the C++'s "not given", not a value the manifest should state.
        if flag is None or scanned is None or scanned == "":
            continue
        stated = _default_value(flag.default, cxx=False) if flag.default is not None else None
        if stated != scanned:
            found.append({
                "kind": "disagreement", "flag": f"-{option}", "source": where,
                "note": f"the manifest's default is {flag.default!r}; the C++ defaults it to {text.strip()}",
            })
    if command_line.arguments and len(command_line.arguments) != len(manifest.positional_args):
        found.append({
            "kind": "disagreement", "flag": None,
            "note": (
                f"the manifest lists {len(manifest.positional_args)} positional arguments; the C++ declares "
                f"{len(command_line.arguments)} ({', '.join(command_line.arguments)})"
            ),
        })
    return [{"utility": manifest.name, **item} for item in found]


def utility_manifest_report(
    repository_root: Path, manifests: Mapping[str, Any], *, utilities: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Each manifest, or each of ``utilities``, compared with the C++ its repository builds it from; a utility the
    repository does not build is listed under ``not_built``, uncompared."""
    root = Path(repository_root).resolve()
    sources = utility_sources(root)
    names = sorted(manifests if utilities is None else set(utilities) & set(manifests))
    findings: list[dict[str, Any]] = []
    for name in names:
        if name in sources:
            findings += compare_manifest(manifests[name], read_command_line(name, sources[name], root=root))
    return {"findings": findings, "not_built": [name for name in names if name not in sources]}
