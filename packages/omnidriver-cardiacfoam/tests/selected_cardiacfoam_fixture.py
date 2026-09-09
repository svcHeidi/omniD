"""Explicit, non-discovering inputs for optional cardiacFoam acceptance tests.

The helpers deliberately perform no staging and never select a checkout from
the host.  Callers may use a returned selection to materialize declared inputs
into a disposable child only after these checks have succeeded.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Mapping


SOURCE_ROOT_ENV = "OMNIDRIVER_CARDIACFOAM_SOURCE_ROOT"
SOURCE_REVISION_ENV = "OMNIDRIVER_CARDIACFOAM_SOURCE_REVISION"
OPENFOAM_BASHRC_ENV = "OPENFOAM_BASHRC"
BACKEND_ENV = "DRIVERFOAM_CARDIACFOAM_BACKEND"
BUILD_MANIFEST_ENV = "DRIVERFOAM_CARDIACFOAM_BUILD_MANIFEST"
OUTPUT_ROOT_ENV = "OMNIDRIVER_NATIVE_OUTPUT_ROOT"
CASE_MANIFEST_ENV = "OMNIDRIVER_CARDIACFOAM_CASE_MANIFEST"
REGRESSION_SCOPE_ENV = "OMNIDRIVER_CARDIACFOAM_REGRESSION_SCOPE"

_REVISION = re.compile(r"[0-9a-f]{40}")
_NATIVE_INPUTS = (
    OPENFOAM_BASHRC_ENV,
    BACKEND_ENV,
    BUILD_MANIFEST_ENV,
    OUTPUT_ROOT_ENV,
    CASE_MANIFEST_ENV,
    REGRESSION_SCOPE_ENV,
)


class FixtureInputError(ValueError):
    """An explicitly requested acceptance fixture is incomplete or unsafe."""


@dataclass(frozen=True)
class SelectedSource:
    root: Path
    revision: str
    src_status: str
    permitted_drift_status: str
    permitted_drift_digest: str
    submodule_status: str


@dataclass(frozen=True)
class SelectedRuntime:
    source: SelectedSource
    openfoam_bashrc: Path
    openfoam_identity: tuple[tuple[str, str], ...]
    backend: str
    build_manifest: Path
    build_manifest_digest: str
    output_root: Path
    case_manifest: Path
    regression_scope: str


def selected_source_from_environment(
    environment: Mapping[str, str] | None = None,
) -> SelectedSource | None:
    """Validate a requested source fixture, or return ``None`` when unselected."""
    env = os.environ if environment is None else environment
    root_value = env.get(SOURCE_ROOT_ENV)
    revision = env.get(SOURCE_REVISION_ENV)
    if not root_value and not revision:
        return None
    if not root_value or not revision:
        raise FixtureInputError(
            f"{SOURCE_ROOT_ENV} and {SOURCE_REVISION_ENV} must be set together"
        )
    if not _REVISION.fullmatch(revision):
        raise FixtureInputError(f"{SOURCE_REVISION_ENV} must be a full 40-character commit id")

    root = _absolute_existing_directory(SOURCE_ROOT_ENV, root_value)
    for required in ("src", "tutorials", ".git"):
        if not (root / required).exists():
            raise FixtureInputError(f"{SOURCE_ROOT_ENV} is missing required {required!r}: {root}")
    head = _git(root, "rev-parse", "HEAD").strip()
    if head != revision:
        raise FixtureInputError(
            f"Selected source HEAD is {head}, not requested revision {revision}"
        )

    src_status = _git(root, "status", "--porcelain", "--", "src")
    if src_status:
        raise FixtureInputError(
            "Selected source has build-affecting src/ drift; fixture refuses before staging: "
            + src_status.strip()
        )
    if _git_exit_code(root, "diff", "--quiet", revision, "--", "src") != 0:
        raise FixtureInputError("Selected source src/ differs from the requested revision")

    # Tutorials and characterization inputs may intentionally be candidates.
    # Record all non-src worktree evidence rather than treating it as a new
    # committed reference or silently reading it during source-only checks.
    permitted_status = _git(root, "status", "--porcelain", "--", ".", ":(exclude)src")
    permitted_diff = _git(root, "diff", "--binary", revision, "--", ".", ":(exclude)src")
    permitted_untracked = _git(
        root, "ls-files", "--others", "--exclude-standard", "--", ".", ":(exclude)src"
    )
    permitted_digest = hashlib.sha256(
        (permitted_diff + "\0" + permitted_untracked).encode("utf-8")
    ).hexdigest()
    return SelectedSource(
        root=root,
        revision=revision,
        src_status=src_status,
        permitted_drift_status=permitted_status,
        permitted_drift_digest="sha256:" + permitted_digest,
        submodule_status=_git(root, "submodule", "status", "--recursive"),
    )


def selected_runtime_from_environment(
    source: SelectedSource | None,
    *,
    repository_root: Path,
    environment: Mapping[str, str] | None = None,
) -> SelectedRuntime | None:
    """Validate a requested native fixture before it can configure or stage."""
    env = os.environ if environment is None else environment
    requested = [key for key in _NATIVE_INPUTS if env.get(key)]
    if not requested:
        return None
    if source is None:
        raise FixtureInputError(
            "Native fixture inputs require an explicitly validated selected source"
        )
    missing = [key for key in _NATIVE_INPUTS if not env.get(key)]
    if missing:
        raise FixtureInputError(
            "Native fixture was requested but is missing: " + ", ".join(missing)
        )

    bashrc = _absolute_existing_file(OPENFOAM_BASHRC_ENV, env[OPENFOAM_BASHRC_ENV])
    if bashrc.name != "bashrc":
        raise FixtureInputError(f"{OPENFOAM_BASHRC_ENV} must name an etc/bashrc file: {bashrc}")
    runtime_environment = _source_openfoam_environment(bashrc)
    openfoam_identity = _openfoam_identity(runtime_environment, bashrc)
    manifest = _absolute_existing_file(BUILD_MANIFEST_ENV, env[BUILD_MANIFEST_ENV])
    case_manifest = _absolute_existing_file(CASE_MANIFEST_ENV, env[CASE_MANIFEST_ENV])
    output_root = _absolute_existing_directory(OUTPUT_ROOT_ENV, env[OUTPUT_ROOT_ENV])
    repository_root = repository_root.resolve()
    if output_root.is_relative_to(source.root) or output_root.is_relative_to(repository_root):
        raise FixtureInputError(
            f"{OUTPUT_ROOT_ENV} must be outside the selected source and OmniDriver checkouts"
        )

    from omnidriver.cardiacfoam.runtime_profile import _profile_contract

    backend = env[BACKEND_ENV]
    if backend not in _profile_contract()["options"]:
        raise FixtureInputError(f"{BACKEND_ENV} is not a declared cardiacFoam backend: {backend!r}")
    scope = env[REGRESSION_SCOPE_ENV].strip()
    if not scope:
        raise FixtureInputError(f"{REGRESSION_SCOPE_ENV} must not be empty")
    configured_input = dict(runtime_environment)
    configured_input.update(
        {key: value for key, value in env.items() if key.startswith("DRIVERFOAM_")}
    )
    solver = shutil.which("cardiacFoam", path=configured_input.get("PATH"))
    if solver is None:
        raise FixtureInputError("Selected OpenFOAM environment does not expose cardiacFoam")
    if manifest.stat().st_mtime < Path(solver).stat().st_mtime:
        raise FixtureInputError(
            "Build manifest is older than cardiacFoam; fixture refuses manifest regeneration"
        )
    from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin

    _, configuration_error = CardiacFoamPlugin().configure_execution_environment(configured_input)
    if configuration_error:
        raise FixtureInputError(
            "Selected build manifest was not accepted by the cardiac adapter: "
            + configuration_error
        )
    return SelectedRuntime(
        source=source,
        openfoam_bashrc=bashrc,
        openfoam_identity=openfoam_identity,
        backend=backend,
        build_manifest=manifest,
        build_manifest_digest="sha256:" + hashlib.sha256(manifest.read_bytes()).hexdigest(),
        output_root=output_root,
        case_manifest=case_manifest,
        regression_scope=scope,
    )


def _absolute_existing_directory(name: str, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute() or not path.is_dir():
        raise FixtureInputError(f"{name} must be an existing absolute directory: {value!r}")
    return path.resolve()


def _absolute_existing_file(name: str, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute() or not path.is_file():
        raise FixtureInputError(f"{name} must be an existing absolute file: {value!r}")
    return path.resolve()


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True
    )
    if result.returncode:
        raise FixtureInputError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def _git_exit_code(root: Path, *args: str) -> int:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True
    ).returncode


def _source_openfoam_environment(bashrc: Path) -> dict[str, str]:
    """Source only the selected bashrc and capture the child environment."""
    result = subprocess.run(
        ["bash", "-c", 'source "$1" && env -0', "omnidriver-selected-runtime", str(bashrc)],
        capture_output=True,
    )
    if result.returncode:
        raise FixtureInputError(
            f"Could not source {OPENFOAM_BASHRC_ENV} {bashrc}: "
            + result.stderr.decode(errors="replace").strip()
        )
    environment: dict[str, str] = {}
    for item in result.stdout.split(b"\0"):
        if not item or b"=" not in item:
            continue
        key, value = item.split(b"=", 1)
        environment[key.decode()] = value.decode()
    return environment


def _openfoam_identity(
    environment: Mapping[str, str], bashrc: Path
) -> tuple[tuple[str, str], ...]:
    """Return the required OpenFOAM identity reported by a sourced bashrc."""
    names = ("WM_PROJECT_DIR", "WM_PROJECT_VERSION", "WM_OPTIONS")
    values = [environment.get(name, "") for name in names]
    if len(values) != len(names) or any(not value for value in values):
        raise FixtureInputError(
            f"{OPENFOAM_BASHRC_ENV} must report non-empty " + ", ".join(names)
        )
    return tuple(zip(names, values, strict=True))
