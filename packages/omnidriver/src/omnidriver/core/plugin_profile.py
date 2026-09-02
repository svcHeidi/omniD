"""Schema-checked declarative metadata supplied by a trusted solver plugin.

Profiles deliberately describe files and C++/Python catalog provenance only.
They are not an execution language: workflow execution and solver semantics
remain Python responsibilities behind the core security boundary.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml


@dataclass(frozen=True)
class CaseFileRule:
    path: str
    kind: str
    role: str
    required: str


@dataclass(frozen=True)
class CxxMapping:
    source_roots: tuple[Path, ...]
    allowlist_path: Path


@dataclass(frozen=True)
class PluginProfile:
    path: Path
    plugin_id: str
    api_version: str
    case_files: tuple[CaseFileRule, ...]
    cxx_mapping: CxxMapping | None
    payload: dict[str, Any]
    _digest: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Snapshot the planning digest before callers can mutate payload data.

        ``payload`` remains available for reporting and compatibility, but it
        is nested YAML/JSON data and therefore cannot be made meaningfully
        immutable without changing its public shape. The context identity must
        nevertheless stay stable for the lifetime of a plan.
        """
        canonical = json.dumps(
            self.payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        ).encode("utf-8")
        object.__setattr__(self, "_digest", "sha256:" + hashlib.sha256(canonical).hexdigest())

    @property
    def digest(self) -> str:
        return self._digest


def _mapping_error(path: Path, message: str) -> ValueError:
    return ValueError(f"Invalid plugin profile {path}: {message}")


#: Case-file roles core recognises. The prefix is load-bearing: ``openfoam.*``
#: marks a file the OpenFOAM runtime itself requires, ``plugin.*`` one the
#: solver plugin requires, ``case.*`` one that belongs to the case as a
#: document rather than to either. Consumers split on that prefix
#: (tutorial_contracts.py) and look up specific roles by exact string
#: (provenance_inputs.py, registry.py), so an unvalidated typo silently
#: reclassifies a file instead of failing. See future/ENVIRONMENT_CONTRACT.md.
#:
#: This set is closed and stays closed -- it is NOT the vocabulary a
#: non-OpenFOAM plugin uses. That plugin declares roles via the
#: ``ESCAPE_ROLE_PREFIX`` tier below instead of adding to this frozenset.
#:
#: Adding a role here is a contract change: document it in
#: core/generic-plugin.yaml's role reference in the same edit.
KNOWN_ROLES: frozenset[str] = frozenset({
    "openfoam.control_dict",
    "openfoam.discretisation",
    "openfoam.solver_settings",
    "openfoam.decomposition",
    "openfoam.mesh_generation",
    "openfoam.case_directory",
    "openfoam.entrypoint",
    "openfoam.cleanup",
    "plugin.configuration",
    "case.documentation",
    "case.regression_test",
})

#: Reserved first-segment words. These are the namespaces core actually
#: validates the leaf of (against ``KNOWN_ROLES`` above); a role using one of
#: them is never eligible for the escape tier below, even if the exact
#: string is not in ``KNOWN_ROLES`` -- that is precisely the typo case the
#: escape tier must NOT swallow.
_RESERVED_ROLE_NAMESPACES: frozenset[str] = frozenset({"openfoam", "plugin", "case"})

#: Escape marker for a case-file role naming an environment core has no
#: vocabulary for at all (FEniCS, deal.II, SU2, ...). A role of the exact
#: shape ``x-<namespace>.<leaf>`` bypasses the closed ``KNOWN_ROLES`` enum;
#: neither ``<namespace>`` nor ``<leaf>`` is checked against a vocabulary,
#: because core does not and should not own one for a foreign environment.
#:
#: What this does NOT do: it does not touch the three reserved namespaces.
#: ``openfoam.controldict``, ``openfoam.control_dickt``, or bare
#: ``control_dict`` still raise -- none of them carry the ``x-`` marker, so
#: they are checked against ``KNOWN_ROLES`` exactly as before and fail. The
#: marker is deliberately a prefix a typo of a reserved namespace cannot
#: land on by accident (``openfoam.*`` -> ``x-openfoam.*`` is not a
#: plausible fat-finger slip), which is the property a bare "unknown
#: namespace passes" rule would not have had: it would have silently
#: accepted ``opnefoam.control_dict`` as if it were a new environment's
#: namespace. See future/ENVIRONMENT_CONTRACT.md §11.
ESCAPE_ROLE_PREFIX = "x-"


def _is_valid_escape_role(role: str) -> bool:
    """True if ``role`` has the escape shape ``x-<namespace>.<leaf>``.

    Both segments must be non-empty, and ``<namespace>`` must not be one of
    the three reserved words -- otherwise a role could dodge the closed-enum
    check by spelling e.g. ``x-openfoam.control_dict``, which would look
    like a genuine core-owned role to any consumer splitting on
    ``role.startswith("openfoam.")`` while never having been validated
    against ``KNOWN_ROLES``.
    """
    if not role.startswith(ESCAPE_ROLE_PREFIX):
        return False
    rest = role[len(ESCAPE_ROLE_PREFIX):]
    namespace, sep, leaf = rest.partition(".")
    if not sep or not namespace or not leaf:
        return False
    return namespace not in _RESERVED_ROLE_NAMESPACES


#: The role naming a case's executable entrypoint. Named here rather than
#: spelled as a literal at each use: before this, three sites independently
#: hardcoded ``"Allrun"`` while a fourth resolved it properly from the role.
ENTRYPOINT_ROLE = "openfoam.entrypoint"

#: Used when no plugin declares an entrypoint. This is a documented default a
#: plugin can override -- not a hardcoded binding -- which is what Rule 1
#: requires of a concrete environment name in core.
DEFAULT_ENTRYPOINT_RELPATHS: tuple[str, ...] = ("Allrun",)

#: Namespaces whose files belong to the plugin or the case rather than to the
#: simulation environment. Everything else -- ``openfoam.*`` and any ``x-``
#: escape for a foreign environment -- is environment-owned.
_NON_ENVIRONMENT_NAMESPACES: frozenset[str] = frozenset({"plugin", "case"})


def is_environment_role(role: str) -> bool:
    """True when ``role`` names a file the simulation environment owns.

    Callers used to ask this as ``role.startswith("openfoam.")``, which was
    right while ``openfoam`` was the only environment namespace and became
    wrong the moment the escape tier admitted others: a FEniCS plugin's
    ``x-fenics.mesh_file`` is as environment-owned as ``openfoam.control_dict``
    is, and a prefix test files it under core's own inputs instead.

    Asking it the other way round -- is this namespace one of the two that are
    NOT an environment -- stays correct as environments are added, because
    ``plugin`` and ``case`` are core's own vocabulary and closed.
    """
    namespace, separator, _ = role.partition(".")
    if not separator:
        return False
    if namespace.startswith(ESCAPE_ROLE_PREFIX):
        return True
    return namespace not in _NON_ENVIRONMENT_NAMESPACES


def _entrypoint_relpaths_from_rules(rules: Iterable[CaseFileRule]) -> tuple[str, ...]:
    declared = tuple(rule.path for rule in rules if rule.role == ENTRYPOINT_ROLE)
    return declared or DEFAULT_ENTRYPOINT_RELPATHS


def entrypoint_relpaths(driver_context: Any | None) -> tuple[str, ...]:
    """Case-relative paths the active plugin declares as its entrypoint.

    Searches every declared rule, not just ``required_rules()``: an entrypoint
    is legitimately ``conditional`` (both shipped profiles declare it so), and
    ``required_rules()`` filters to ``required == "always"``.
    """
    if driver_context is None:
        return DEFAULT_ENTRYPOINT_RELPATHS
    return _entrypoint_relpaths_from_rules(driver_context.capabilities.case_files.all_rules())


def entrypoint_relpaths_from_profile(profile: PluginProfile) -> tuple[str, ...]:
    """Same rule as :func:`entrypoint_relpaths`, but reading a
    :class:`PluginProfile` directly rather than through a ``DriverContext``.

    For a plugin's own ``get_capabilities()``, which runs before any
    ``DriverContext`` necessarily wraps it -- a ``DriverContext`` is
    constructed *from* a validated plugin, not the reverse -- but which
    already has its own profile via ``self.get_profile()``. See
    future/CASE_SCRIPT_COMMANDS_ENTRYPOINT_THREAT_MODEL.md §5.
    """
    return _entrypoint_relpaths_from_rules(profile.case_files)


def entrypoint_command(driver_context: Any | None) -> str:
    """The single command name a generated workflow step should invoke.

    A workflow step names one command; ``entrypoint_relpaths`` may return
    several. The first declared wins, which matches what ``_has_entrypoint``
    already treats as sufficient for case detection.
    """
    return entrypoint_relpaths(driver_context)[0]


#: Documented default for :func:`decomposition_dirname_prefix` -- OpenFOAM's
#: own domain-decomposition convention, not a hardcoded binding: a plugin
#: overrides it via ``get_decomposition_dirname_prefix()``. See
#: future/ENVIRONMENT_CONTRACT.md §10, Tier 3.
DEFAULT_DECOMPOSITION_DIRNAME_PREFIX = "processor"


def decomposition_dirname_prefix(driver_context: Any | None) -> str:
    """Dirname prefix a parallel run's per-rank output directories share
    (``processor0``, ``processor1``, ... for OpenFOAM). Not a ``CaseFileRule``
    role -- a role names one static path, and this names a wildcard family --
    so it is a bare optional hook via ``CaseFileContractCapability``, with
    ``driver_context=None`` (no active plugin) using the documented default
    directly, same as :func:`entrypoint_relpaths`.
    """
    if driver_context is None:
        return DEFAULT_DECOMPOSITION_DIRNAME_PREFIX
    return driver_context.capabilities.case_files.decomposition_dirname_prefix()


def load_plugin_profile(path: str | Path) -> PluginProfile:
    """Load a small, safe YAML profile and convert it into immutable data.

    YAML anchors, tags, templates, and executable values are intentionally not
    interpreted.  ``safe_load`` plus this narrow shape check ensures profile
    data cannot become an alternative plugin execution mechanism.
    """

    profile_path = Path(path).resolve()
    try:
        raw = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise _mapping_error(profile_path, str(exc)) from exc
    except yaml.YAMLError as exc:
        raise _mapping_error(profile_path, f"invalid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise _mapping_error(profile_path, "top level must be a mapping")
    if raw.get("schema_version") != 1:
        raise _mapping_error(profile_path, "schema_version must be 1")
    plugin = raw.get("plugin")
    if not isinstance(plugin, dict):
        raise _mapping_error(profile_path, "plugin must be a mapping")
    plugin_id = plugin.get("id")
    api_version = plugin.get("api_version")
    if not isinstance(plugin_id, str) or not plugin_id:
        raise _mapping_error(profile_path, "plugin.id must be a non-empty string")
    if not isinstance(api_version, str) or not api_version:
        raise _mapping_error(profile_path, "plugin.api_version must be a non-empty string")

    case_profile = raw.get("case_profile", {})
    if not isinstance(case_profile, dict):
        raise _mapping_error(profile_path, "case_profile must be a mapping")
    rules: list[CaseFileRule] = []
    for index, item in enumerate(case_profile.get("dictionaries", ())):
        if not isinstance(item, dict):
            raise _mapping_error(profile_path, f"case_profile.dictionaries[{index}] must be a mapping")
        values = {key: item.get(key) for key in ("path", "kind", "role", "required")}
        if not all(isinstance(value, str) and value for value in values.values()):
            raise _mapping_error(
                profile_path,
                f"case_profile.dictionaries[{index}] requires non-empty path/kind/role/required strings",
            )
        if Path(values["path"]).is_absolute() or ".." in Path(values["path"]).parts:
            raise _mapping_error(profile_path, f"case file path escapes the case: {values['path']!r}")
        if values["required"] not in {"always", "never", "conditional"}:
            raise _mapping_error(
                profile_path,
                "required currently supports only 'always', 'never', or 'conditional'",
            )
        if values["role"] not in KNOWN_ROLES and not _is_valid_escape_role(values["role"]):
            raise _mapping_error(
                profile_path,
                f"unknown case-file role {values['role']!r}; known roles are "
                + ", ".join(sorted(KNOWN_ROLES))
                + f", or an escape role of the form {ESCAPE_ROLE_PREFIX}<namespace>.<leaf> "
                + "for an environment core has no vocabulary for, e.g. "
                + f"{ESCAPE_ROLE_PREFIX}fenics.mesh_file "
                + "(see future/ENVIRONMENT_CONTRACT.md)",
            )
        rules.append(CaseFileRule(**values))

    raw_mapping = raw.get("cxx_mapping")
    cxx_mapping: CxxMapping | None = None
    if raw_mapping is not None:
        if not isinstance(raw_mapping, dict):
            raise _mapping_error(profile_path, "cxx_mapping must be a mapping")
        roots = raw_mapping.get("source_roots")
        allowlist = raw_mapping.get("reviewed_allowlist")
        if not isinstance(roots, list) or not roots or not all(isinstance(item, str) and item for item in roots):
            raise _mapping_error(profile_path, "cxx_mapping.source_roots must be a non-empty string list")
        if not isinstance(allowlist, str) or not allowlist:
            raise _mapping_error(profile_path, "cxx_mapping.reviewed_allowlist must be a string")
        cxx_mapping = CxxMapping(
            source_roots=tuple((profile_path.parent / item).resolve() for item in roots),
            allowlist_path=(profile_path.parent / allowlist).resolve(),
        )

    return PluginProfile(
        path=profile_path,
        plugin_id=plugin_id,
        api_version=api_version,
        case_files=tuple(rules),
        cxx_mapping=cxx_mapping,
        payload=raw,
    )
