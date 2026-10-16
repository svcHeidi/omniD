"""Each solver's builds a plan uses, as the run document's ``solverProvenance`` list, and the
preflight that compares their source with the supplied repository."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

from ..planning_types import StrictDiagnostic, diagnostic
from ..plugin_interface import SolverBuild, SolverEntry, SourceIdentity
from .provenance_inputs import runtime_dependencies


def solver_entries(
    case_root: Path, *, workflow_dag: dict[str, Any] | None, driver_context: Any, env: Mapping[str, str],
) -> tuple[SolverEntry, ...]:
    """The stack's ``get_solver_builds``, limited to the paths this plan runs."""
    dependencies = runtime_dependencies(case_root, workflow_dag=workflow_dag, driver_context=driver_context, env=env)
    used = frozenset(Path(d.path).resolve() for d in dependencies.values() if d.path is not None)
    return tuple(driver_context.stack.call(
        "get_solver_builds", env, repository=driver_context.repository, used_paths=used,
    ))


def matches(build: SolverBuild, repository: SourceIdentity | None) -> bool | None:
    """Whether ``build`` came from ``repository``, by digest; ``None`` when either digest is unknown."""
    if build.source is None or build.source.digest is None or repository is None or repository.digest is None:
        return None
    return build.source.digest == repository.digest


def to_json(entries: Iterable[SolverEntry]) -> list[dict[str, Any]]:
    return [
        {
            "solver": entry.solver,
            "repository": entry.repository.to_json() if entry.repository is not None else None,
            "builds": [
                {
                    "name": build.name,
                    "path": str(build.path) if build.path is not None else None,
                    "digest": build.digest,
                    "known": build.known,
                    "source": build.source.to_json() if build.source is not None else None,
                    "matchesRepository": matches(build, entry.repository),
                }
                for build in entry.builds
            ],
        }
        for entry in entries
    ]


def provenance_diagnostics(entries: Iterable[SolverEntry]) -> tuple[StrictDiagnostic, ...]:
    """``stale_build`` for builds recorded from other source than the supplied repository, one per
    solver and source; ``build_source_unknown`` for builds nothing identifies, one per solver."""
    found: list[StrictDiagnostic] = []
    for entry in entries:
        elsewhere: dict[tuple[Any, ...], list[SolverBuild]] = {}
        unknown: list[SolverBuild] = []
        for build in entry.builds:
            if build.known == "unknown":
                unknown.append(build)
            elif matches(build, entry.repository) is False:
                key = (build.source.repository, build.source.digest, _commit(build.source))
                elsewhere.setdefault(key, []).append(build)
        for builds in elsewhere.values():
            source = builds[0].source
            found.append(diagnostic(
                "warning", "stale_build",
                f"{entry.solver}: {_names(builds)} {_were(builds)} built from {_describe(source)}, but the plan "
                f"reads {_describe(entry.repository)}: the plan and the scan describe source these builds were "
                "not made from; rebuild from the supplied repository and record the build",
                source="environment", field=builds[0].name,
                detail={"solver": entry.solver, "builds": [b.name for b in builds],
                        "built_from": source.to_json(), "supplied": entry.repository.to_json()},
            ))
        if unknown:
            hint = (
                f"; after building, run `omnidriver build-record --repo {entry.repository.repository}`"
                if entry.recordable and entry.repository is not None and entry.repository.repository else ""
            )
            found.append(diagnostic(
                "info", "build_source_unknown",
                f"{entry.solver}: nothing states which source built {_names(unknown)}{hint}",
                source="environment", field=unknown[0].name,
            ))
    return tuple(found)


def _commit(identity: SourceIdentity) -> str | None:
    return (identity.git or {}).get("commit")


def _describe(identity: SourceIdentity) -> str:
    git = identity.git or {}
    label = git.get("commit") or "no git commit"
    if git.get("dirty"):
        label += ", with uncommitted changes"
    return f"{identity.repository} ({label}; {identity.digest})"


def _names(builds: list[SolverBuild]) -> str:
    return ", ".join(build.name for build in builds)


def _were(builds: list[SolverBuild]) -> str:
    return "was" if len(builds) == 1 else "were"
