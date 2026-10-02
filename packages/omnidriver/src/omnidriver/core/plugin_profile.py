"""Schema-checked declarative metadata supplied by a trusted solver plugin.

Profiles deliberately describe files and C++/Python catalog provenance only.
They are not an execution language: workflow execution and solver semantics
remain Python responsibilities behind the core security boundary.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml



@dataclass(frozen=True)
class CaseFileRule:
    path: str
    kind: str
    role: str
    required: str


@dataclass(frozen=True)
class CxxMapping:
    """Where the plugin's C++ source is, and its reviewed scanner mapping.

    The source root is supplied, never discovered (CLAUDE.md): the profile
    names the supplied variable that holds the native tree and the C++
    source's place inside it (``relative``, the native repository's own
    layout). A root that nobody supplied is ``None``, never a guess.
    """

    source_root_variable: str
    source_root_relative: str
    allowlist_path: Path

    def source_root(self, environ: Mapping[str, str]) -> Path | None:
        value = environ.get(self.source_root_variable)
        if not value:
            return None
        return (Path(value).expanduser() / self.source_root_relative).resolve()


@dataclass(frozen=True)
class SuppliedVariable:
    name: str
    required: bool
    why: str


@dataclass(frozen=True)
class EnvironmentConnection:
    """How a shell must be prepared to run this plugin's commands.

    ``supplied`` are variables the operator sets; nothing here holds a value.
    ``source`` names the supplied variable whose file is sourced first;
    every set supplied variable is exported after it (macOS strips
    ``DYLD_*`` when bash starts, so an export before ``source`` is lost);
    ``path_prepend`` names supplied directories put first on ``PATH``;
    ``mpi_launcher`` is the launcher command a parallel run uses.
    """

    supplied: tuple[SuppliedVariable, ...] = ()
    source: str | None = None
    path_prepend: tuple[str, ...] = ()
    mpi_launcher: str | None = None


@dataclass(frozen=True)
class PluginProfile:
    #: ``None`` for the profile of a provider that declares none.
    path: Path | None
    plugin_id: str
    api_version: str
    case_files: tuple[CaseFileRule, ...]
    cxx_mapping: CxxMapping | None
    payload: dict[str, Any]
    environment: EnvironmentConnection | None = None
    #: Provider ids this one layers on top of, least-specific first. Ordering
    #: is declared, never inferred from install order or entry-point name.
    requires: tuple[str, ...] = ()
    _digest: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Snapshot the planning digest before callers can mutate payload data.

        ``payload`` remains available for reporting and compatibility, but it
        is nested YAML/JSON data and therefore cannot be made meaningfully
        immutable without changing its public shape. The context identity must
        nevertheless stay stable for the lifetime of a plan.

        ``requires`` is folded in explicitly, alongside ``payload``: a
        provider that changes what it requires has changed its semantics,
        whether or not the key survives verbatim inside ``payload``.
        """
        canonical = json.dumps(
            {
                "payload": self.payload,
                "requires": list(self.requires),
            },
            sort_keys=True, separators=(",", ":"), ensure_ascii=True,
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


def entrypoint_relpaths(driver_context: Any | None) -> tuple[str, ...]:
    """Case-relative executable paths declared by the active environment.

    An entrypoint is an execution convention, rather than a file-role that
    Core interprets.  The adapter therefore supplies it through
    :class:`CaseRuntimeConventions`; Core only uses the declared path for case
    discovery, generated workflows, and case-local command authorization.
    """
    if driver_context is None:
        return ()
    from .runtime_records import case_runtime_conventions

    return tuple(case_runtime_conventions(driver_context).case_entrypoints)


def replica_directory_globs(driver_context: Any | None) -> tuple[str, ...]:
    """Parallel-replica directory globs declared by the active environment."""
    if driver_context is None:
        return ()
    from .runtime_records import case_runtime_conventions

    return tuple(case_runtime_conventions(driver_context).replica_directory_globs)


def is_replica_directory_name(name: str, globs: tuple[str, ...]) -> bool:
    """Whether a directory name, at any depth in the case tree, is one of
    the declared replicas. Every caller (``registry``, ``sweep_runner``)
    applies this at every depth, not only the case root."""
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in globs)


def _environment_connection(profile_path: Path, raw: Any) -> EnvironmentConnection | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise _mapping_error(profile_path, "environment must be a mapping")
    unknown = sorted(set(raw) - {"supplied", "source", "path_prepend", "mpi_launcher"})
    if unknown:
        raise _mapping_error(profile_path, f"environment has unknown keys {unknown}")
    supplied = []
    for index, item in enumerate(raw.get("supplied", ())):
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("name"), str) or not item["name"]
            or not isinstance(item.get("required"), bool)
            or not isinstance(item.get("why"), str) or not item["why"]
        ):
            raise _mapping_error(
                profile_path,
                f"environment.supplied[{index}] needs a name, a boolean 'required' and a 'why'",
            )
        supplied.append(SuppliedVariable(item["name"], item["required"], item["why"]))
    names = {item.name for item in supplied}
    source = raw.get("source")
    path_prepend = tuple(raw.get("path_prepend", ()) or ())
    for name in ((source,) if source is not None else ()) + path_prepend:
        if name not in names:
            raise _mapping_error(
                profile_path, f"environment names {name!r}, which is not one of its supplied variables",
            )
    launcher = raw.get("mpi_launcher")
    if launcher is not None and (not isinstance(launcher, str) or not launcher):
        raise _mapping_error(profile_path, "environment.mpi_launcher must be a command name")
    return EnvironmentConnection(
        supplied=tuple(supplied), source=source, path_prepend=path_prepend, mpi_launcher=launcher,
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
        root = raw_mapping.get("source_root")
        allowlist = raw_mapping.get("reviewed_allowlist")
        if (
            not isinstance(root, dict)
            or not isinstance(root.get("variable"), str) or not root["variable"]
            or not isinstance(root.get("relative"), str) or not root["relative"]
        ):
            raise _mapping_error(
                profile_path,
                "cxx_mapping.source_root must be a mapping with non-empty 'variable' "
                "(the supplied variable naming the native tree) and 'relative' "
                "(the C++ source inside it)",
            )
        if not isinstance(allowlist, str) or not allowlist:
            raise _mapping_error(profile_path, "cxx_mapping.reviewed_allowlist must be a string")
        cxx_mapping = CxxMapping(
            source_root_variable=root["variable"],
            source_root_relative=root["relative"],
            allowlist_path=(profile_path.parent / allowlist).resolve(),
        )

    environment = _environment_connection(profile_path, raw.get("environment"))

    requires = tuple(raw.get("requires", ()) or ())

    return PluginProfile(
        path=profile_path,
        plugin_id=plugin_id,
        api_version=api_version,
        case_files=tuple(rules),
        cxx_mapping=cxx_mapping,
        payload=raw,
        environment=environment,
        requires=requires,
    )
