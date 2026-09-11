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
from typing import Any

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


#: Roles whose meaning belongs to Core. Environment role names are adapter
#: data: Core validates their shape and ownership, never their vocabulary.
KNOWN_ROLES: frozenset[str] = frozenset({
    "plugin.configuration",
    "case.documentation",
    "case.regression_test",
})

#: Reserved first-segment words. These are the namespaces core actually
#: validates the leaf of (against ``KNOWN_ROLES`` above); a role using one of
#: them is never eligible for the escape tier below, even if the exact
#: string is not in ``KNOWN_ROLES`` -- that is precisely the typo case the
#: escape tier must NOT swallow.
_RESERVED_ROLE_NAMESPACES: frozenset[str] = frozenset({"plugin", "case"})

#: Compatibility marker for existing foreign-environment profiles. New
#: adapters may declare their own namespace directly (``fenics.mesh_file``);
#: their adapter validates its vocabulary.
ESCAPE_ROLE_PREFIX = "x-"


def _is_valid_environment_role(role: str) -> bool:
    """True for an adapter-owned ``namespace.leaf`` role name."""
    namespace, separator, leaf = role.partition(".")
    if not separator or not namespace or not leaf:
        return False
    effective_namespace = namespace[len(ESCAPE_ROLE_PREFIX):] if namespace.startswith(ESCAPE_ROLE_PREFIX) else namespace
    if not effective_namespace or effective_namespace in _RESERVED_ROLE_NAMESPACES:
        return False
    return all(part.replace("_", "").replace("-", "").isalnum() for part in (namespace, leaf))


#: Namespaces whose files belong to the plugin or the case rather than to the
#: simulation environment. Every other validated namespace is adapter-owned.
_NON_ENVIRONMENT_NAMESPACES: frozenset[str] = frozenset({"plugin", "case"})


def is_environment_role(role: str) -> bool:
    """True when ``role`` names a file the simulation environment owns.

    Core owns only the ``plugin`` and ``case`` namespaces. An adapter owns
    every other validated namespace, including a legacy ``x-`` namespace.
    """
    namespace, separator, _ = role.partition(".")
    if not separator:
        return False
    return namespace not in _NON_ENVIRONMENT_NAMESPACES


def entrypoint_relpaths(driver_context: Any | None) -> tuple[str, ...]:
    """Case-relative executable paths declared by the active environment.

    An entrypoint is an execution convention, rather than a file-role that
    Core interprets.  The adapter therefore supplies it through
    :class:`CaseRuntimeConventions`; Core only uses the declared path for case
    discovery, generated workflows, and case-local command authorization.
    """
    if driver_context is None:
        return ()
    return tuple(
        driver_context.capabilities.case_runtime_conventions.conventions()
        .case_entrypoints
    )


def entrypoint_command(driver_context: Any | None) -> str:
    """The single command name a generated workflow step should invoke.

    A workflow step names one command; ``entrypoint_relpaths`` may return
    several. The first declared wins, which matches what ``_has_entrypoint``
    already treats as sufficient for case detection.
    """
    paths = entrypoint_relpaths(driver_context)
    if not paths:
        raise ValueError("The active environment did not declare a case entrypoint.")
    return paths[0]


def decomposition_dirname_prefix(driver_context: Any | None) -> str | None:
    """Parallel-output prefix declared by the active environment."""
    if driver_context is None:
        return None
    return (
        driver_context.capabilities.case_runtime_conventions.conventions()
        .decomposition_directory_prefix
    )


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
        if values["role"] not in KNOWN_ROLES and not _is_valid_environment_role(values["role"]):
            raise _mapping_error(
                profile_path,
                f"invalid case-file role {values['role']!r}; Core roles are "
                + ", ".join(sorted(KNOWN_ROLES))
                + "; an environment role must have the form namespace.leaf",
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
