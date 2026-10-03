"""Where cardiacFoam's runtime evidence lives: solve steps, log locations, extra provenance inputs and artifact readers."""

from __future__ import annotations

import os
import re
import shutil
from collections.abc import Mapping
from pathlib import Path

from omnidriver.core.plugin_interface import RuntimeDependency

# Commands that run the solver. Deliberately excludes
# bathBidomainInterfaceMetrics, which is authorized to run but post-processes
# rather than solves -- expecting solver telemetry from it would be wrong.
_SOLVE_STEP_COMMANDS = frozenset({"cardiacFoam"})

def solve_step_commands() -> frozenset[str]:
    return _SOLVE_STEP_COMMANDS


# Libraries cardiacFoam links or loads, and whether their absence is abnormal.
#
# required=True  -- linked unconditionally into cardiacFoam's EXE_LIBS
#                    (applications/solvers/cardiacFoam/Make/options); the
#                    solver cannot start without it.
# required=False -- either mode-dependent (exactly one of physicsModel /
#                    electroMechanicalModels is linked, selected by
#                    USE_LIGHTWEIGHT_PHYSICSMODEL at build time, which cannot
#                    be told from outside the binary) or not linked at all
#                    (verificationModels): the cases that use it name it in
#                    their own controlDict libs, which makes it required for
#                    them; see _resolve_control_dict_libs_entry.
_LIBRARY_CATALOG: dict[str, bool] = {
    "electroModels": True,
    "ionicModels": True,
    "genericWriter": True,
    "activeTensionModels": True,
    "physicsModel": False,
    "electroMechanicalModels": False,
    "verificationModels": False,
}

# Search every defined one, never one fixed variable per name: a plain sourced
# shell leaves FOAM_MODULE_LIBBIN unset, and libphysicsModel is found in
# FOAM_USER_LIBBIN although its Make/files declares FOAM_MODULE_LIBBIN.
_LIB_DIR_ENV_VARS = ("FOAM_USER_LIBBIN", "FOAM_MODULE_LIBBIN", "FOAM_LIBBIN")

# The extension is platform-dependent -- .dylib here, .so on Linux. Try both
# rather than branching on sys.platform.
_LIB_EXTENSIONS = (".dylib", ".so")

_BARE_LIB_RE = re.compile(r"^lib(.+)\.(?:so|dylib)$")
_ENV_VAR_RE = re.compile(r"\$\{(\w+)\}|\$(\w+)")


def _defined_lib_dirs(env: Mapping[str, str]) -> tuple[Path, ...]:
    return tuple(Path(env[var]) for var in _LIB_DIR_ENV_VARS if env.get(var))


def _resolve_named_library(name: str, *, lib_dirs: tuple[Path, ...]) -> Path | None:
    for lib_dir in lib_dirs:
        for extension in _LIB_EXTENSIONS:
            candidate = lib_dir / f"lib{name}{extension}"
            if candidate.is_file():
                return candidate
    return None


def _parse_control_dict_libs(control_dict_path: Path) -> tuple[str, ...]:
    """The entries of a controlDict's ``libs ( ... )`` list; an absent or unparseable list gives ``()``."""
    from foamlib import FoamFile

    try:
        libs = FoamFile(control_dict_path).get("libs")
    except (OSError, ValueError):
        return ()
    if not libs:
        return ()
    return tuple(_strip_quotes(str(entry)) for entry in libs)


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    return value


def _library_name_from_entry(entry: str) -> str:
    basename = entry.rsplit("/", 1)[-1]
    match = _BARE_LIB_RE.match(basename)
    return match.group(1) if match else basename


def _expand_openfoam_path(raw: str, *, case_root: Path, env: Mapping[str, str]) -> str | None:
    """Expand ``$VAR`` in a controlDict path from ``env`` (``$FOAM_CASE`` is ``case_root``); None when a variable is undefined."""
    # etc/bashrc does not set $FOAM_CASE: OpenFOAM substitutes it at solver startup.
    missing: list[str] = []

    def _substitute(match: "re.Match[str]") -> str:
        name = match.group(1) or match.group(2)
        if name == "FOAM_CASE":
            return str(case_root)
        value = env.get(name)
        if value is None:
            missing.append(name)
            return ""
        return value

    expanded = _ENV_VAR_RE.sub(_substitute, raw)
    return None if missing else expanded


def _resolve_control_dict_libs_entry(
    entry: str,
    *,
    case_root: Path,
    lib_dirs: tuple[Path, ...],
    env: Mapping[str, str],
) -> tuple[str, Path | None]:
    name = _library_name_from_entry(entry)
    if "/" not in entry:
        # A bare entry such as "libverificationModels.so" -- search the
        # defined lib directories exactly like the fixed catalog.
        return name, _resolve_named_library(name, lib_dirs=lib_dirs)

    # A case-local path such as
    # "$FOAM_CASE/platforms/$WM_OPTIONS/lib/lib<name>.so".
    expanded = _expand_openfoam_path(entry, case_root=case_root, env=env)
    if expanded is None:
        return name, None
    candidate = Path(expanded)
    return name, candidate if candidate.is_file() else None


def resolve_runtime_dependencies(
    case_root: Path,
    *,
    env: Mapping[str, str] | None = None,
) -> tuple[RuntimeDependency, ...]:
    """The cardiacFoam binary, the libraries it links or loads, and anything
    this case's own controlDict pulls in through ``libs ( ... )``.

    Most cases run through an ``Allrun`` script, so a workflow step's command
    fingerprints the script, never the solver binary the script invokes.
    Declaring the binary and its libraries here, independent of how a step
    happens to be launched, is what makes a rebuilt solver visible to
    provenance.

    ``env`` defaults to ``os.environ`` (the executor's own environment); a
    test may inject a synthetic mapping so these dependencies resolve
    without a sourced OpenFOAM install.
    """
    environment = os.environ if env is None else env
    case_root = Path(case_root)
    lib_dirs = _defined_lib_dirs(environment)

    dependencies: dict[str, RuntimeDependency] = {}

    solver_path = shutil.which("cardiacFoam", path=environment.get("PATH"))
    dependencies["cardiacFoam"] = RuntimeDependency(
        name="cardiacFoam",
        path=Path(solver_path) if solver_path else None,
        required=True,
    )

    for name, required in _LIBRARY_CATALOG.items():
        dependencies[name] = RuntimeDependency(
            name=name,
            path=_resolve_named_library(name, lib_dirs=lib_dirs),
            required=required,
        )

    control_dict = case_root / "system" / "controlDict"
    if control_dict.is_file():
        for entry in _parse_control_dict_libs(control_dict):
            name, resolved = _resolve_control_dict_libs_entry(
                entry, case_root=case_root, lib_dirs=lib_dirs, env=environment,
            )
            # A case that names a library in its own controlDict cannot run
            # without it -- required regardless of the fixed catalog's
            # default above: six manufactured-solution tutorials depend on
            # exactly this for libverificationModels.
            dependencies[name] = RuntimeDependency(name=name, path=resolved, required=True)

    # A case carrying a gmsh geometry cannot mesh without the gmsh binary.
    # Same case-local reasoning as the controlDict libs above: the case itself
    # says what it needs, rather than a fixed list saying it for every case.
    # Declaring it here surfaces a missing gmsh at plan time, rather than as
    # a workflow step dying mid-run.
    if any(case_root.rglob("*.geo")):
        gmsh_path = shutil.which("gmsh", path=environment.get("PATH"))
        dependencies["gmsh"] = RuntimeDependency(
            name="gmsh",
            path=Path(gmsh_path) if gmsh_path else None,
            required=True,
        )

    return tuple(dependencies.values())


def extra_provenance_paths(case_root: Path) -> tuple[RuntimeDependency, ...]:
    """Runtime dependencies the provenance snapshot must fingerprint beyond
    ``system/`` and ``constant/``: a missing required library is reported,
    never silently omitted."""
    return resolve_runtime_dependencies(case_root)


def artifact_value_reader(artifact_format: str):
    """Reader for a solver-specific artifact format, or ``None``.

    Returning ``None`` must make that consumer report ``not_evaluated`` with
    a reason -- never an implicit pass.

    Returns :class:`~omnidriver.cardiacfoam.activation_probes.ActivationProbeReader`
    for ``ACTIVATION_PROBES_FORMAT``, the format ``niederer2011``'s
    ``samplePoints`` output declares."""
    from omnidriver.cardiacfoam.activation_probes import ACTIVATION_PROBES_FORMAT, ActivationProbeReader

    if artifact_format == ACTIVATION_PROBES_FORMAT:
        return ActivationProbeReader()
    return None
