"""Explicit, non-discovering inputs for optional cardiacFoam acceptance tests.

The helpers deliberately perform no staging and never select a checkout from
the host.  Callers may use a returned selection to materialize declared inputs
into a disposable child only after these checks have succeeded.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
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
_SHA256 = re.compile(r"[0-9a-f]{64}")
_CASE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
_NATIVE_INPUTS = (
    OPENFOAM_BASHRC_ENV,
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


@dataclass(frozen=True)
class CaseInput:
    source: Path
    destination: Path
    sha256: str


@dataclass(frozen=True)
class CaseInputManifest:
    case_id: str
    input_policy: str
    inputs: tuple[CaseInput, ...]


@dataclass(frozen=True)
class StagedInputs:
    root: Path
    case_id: str
    input_policy: str
    input_digest: str
    files: tuple[tuple[str, str], ...]


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

    configured_runtime, configuration_error = CardiacFoamPlugin().configure_execution_environment(
        configured_input
    )
    if configuration_error:
        raise FixtureInputError(
            "Selected build manifest was not accepted by the cardiac adapter: "
            + configuration_error
        )
    backend = configured_runtime.get(BACKEND_ENV)
    if backend not in _profile_contract()["options"]:
        raise FixtureInputError("Cardiac adapter did not resolve a declared runtime backend")
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


def load_case_input_manifest(runtime: SelectedRuntime) -> CaseInputManifest:
    """Read a named input manifest without consulting tutorial markers."""
    try:
        payload = json.loads(runtime.case_manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FixtureInputError(f"Invalid case input manifest {runtime.case_manifest}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise FixtureInputError("Case input manifest requires schema_version 1")
    case_id = payload.get("case_id")
    if not isinstance(case_id, str) or not _CASE_ID.fullmatch(case_id):
        raise FixtureInputError("Case input manifest requires a safe case_id")
    input_policy = payload.get("input_policy", "committed")
    if input_policy not in {"committed", "candidate"}:
        raise FixtureInputError("Case input manifest input_policy must be committed or candidate")
    raw_inputs = payload.get("inputs")
    if not isinstance(raw_inputs, list) or not raw_inputs:
        raise FixtureInputError("Case input manifest requires a non-empty inputs list")

    inputs: list[CaseInput] = []
    destinations: set[Path] = set()
    for index, item in enumerate(raw_inputs):
        if not isinstance(item, dict):
            raise FixtureInputError(f"Case input {index} must be an object")
        source = _relative_manifest_path(item.get("source"), f"inputs[{index}].source")
        destination = _relative_manifest_path(
            item.get("destination"), f"inputs[{index}].destination"
        )
        digest = item.get("sha256")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise FixtureInputError(f"Case input {index} requires a sha256 digest")
        if destination in destinations:
            raise FixtureInputError(f"Case input manifest repeats destination {destination}")
        destinations.add(destination)
        inputs.append(CaseInput(source=source, destination=destination, sha256=digest))
    return CaseInputManifest(case_id=case_id, input_policy=input_policy, inputs=tuple(inputs))


def materialize_case_inputs(
    runtime: SelectedRuntime, manifest: CaseInputManifest
) -> StagedInputs:
    """Materialize declared bytes into one unique child of the output root.

    Committed mode reads bytes with git show at the selected revision.
    Candidate mode is explicit in the named manifest and stages only declared
    current-worktree files.  Neither mode discovers tutorials or writes source.
    """
    stage_root = Path(
        tempfile.mkdtemp(prefix=f"omnidriver-{manifest.case_id}-", dir=runtime.output_root)
    )
    files: list[tuple[str, str]] = []
    for item in manifest.inputs:
        if manifest.input_policy == "committed":
            content = _git_bytes(
                runtime.source.root,
                "show",
                f"{runtime.source.revision}:{item.source.as_posix()}",
            )
        else:
            candidate = runtime.source.root / item.source
            if not candidate.is_file():
                raise FixtureInputError(f"Candidate input does not exist: {item.source}")
            content = candidate.read_bytes()
        actual_digest = hashlib.sha256(content).hexdigest()
        if actual_digest != item.sha256:
            raise FixtureInputError(
                f"Declared digest for {item.source} does not match selected {manifest.input_policy} bytes"
            )
        target = stage_root / item.destination
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        files.append((item.destination.as_posix(), "sha256:" + actual_digest))
    digest_payload = json.dumps(
        {"case_id": manifest.case_id, "input_policy": manifest.input_policy, "files": files},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return StagedInputs(
        root=stage_root,
        case_id=manifest.case_id,
        input_policy=manifest.input_policy,
        input_digest="sha256:" + hashlib.sha256(digest_payload).hexdigest(),
        files=tuple(files),
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


def _relative_manifest_path(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise FixtureInputError(f"{label} must be a non-empty forward-slash relative path")
    path = Path(value)
    if path.is_absolute() or path == Path(".") or ".." in path.parts:
        raise FixtureInputError(f"{label} must stay below the selected fixture root: {value!r}")
    return path


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


def _git_bytes(root: Path, *args: str) -> bytes:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    if result.returncode:
        raise FixtureInputError(
            result.stderr.decode(errors="replace").strip() or f"git {' '.join(args)} failed"
        )
    return result.stdout


def _source_openfoam_environment(bashrc: Path) -> dict[str, str]:
    """Source only the selected bashrc and capture the child environment."""
    # OpenFOAM's bashrc forwards positional arguments to its setup script.
    # Keep the selected path in a local variable, then clear ``$@`` before
    # sourcing so the bashrc is not recursively interpreted as a config file.
    result = subprocess.run(
        [
            "bash",
            "-c",
            'bashrc=$1; shift; source "$bashrc" && exec /usr/bin/env -0',
            "omnidriver-selected-runtime",
            str(bashrc),
        ],
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
