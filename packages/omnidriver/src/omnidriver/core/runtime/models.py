from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Final


ArtifactFormat = str
"""Artifact output format. Open-ended by design, not a closed enum: nothing
in core branches on this value today, and most format strings in practice
(``openfoam_log``, ``vtk_sequence``, ``csv_probe``, ``openfoam_time_dirs``,
...) are a solver plugin's own vocabulary for its own outputs -- core has no
business validating spellings it does not own (future/ENVIRONMENT_CONTRACT.md
§10, Tier 3). ``CORE_ARTIFACT_FORMATS`` below names the only two values core
itself ever writes, for its own artifacts."""

CORE_ARTIFACT_FORMATS: Final[frozenset[str]] = frozenset({"json_summary", "log"})
"""Format values used by artifacts core predicts for itself (see
``runtime/artifacts.py``'s generic-case fallback) -- not a validation gate
on plugin-declared formats, which may be anything."""


@dataclass(frozen=True)
class DataArtifact:
    """Declarative description of a raw data output produced by a run or utility.

    Shared vocabulary between the engine and ``utility.manifest.toml`` ``produces``
    entries (which declare what a utility writes). Agents consume both through
    the same shape.

    ``path_pattern`` is case-relative. The only recognised placeholders are
    ``{case_id}`` (substituted with the sweep case identifier) and ``{time}``
    (substituted with an OpenFOAM time directory name). Anything else is a
    literal path component.
    """

    artifact_id: str
    """Stable identifier within the manifest. Predictor merges static + derived
    artifacts by ``artifact_id`` (static wins on collision)."""

    path_pattern: str
    """Case-relative path; may contain ``{case_id}`` / ``{time}`` placeholders."""

    format: ArtifactFormat
    """One of the documented :data:`ArtifactFormat` values."""

    variables: tuple[str, ...] = ()
    """Per-variable structure inside the file. ``()`` means "no per-variable
    structure" (e.g., an opaque log). Never ``None`` — ambiguity-free merging
    in the predictor depends on this."""

    description: str = ""
    """Human-readable purpose. May be empty."""

    produced_by: str = ""
    """Solver or utility name that writes this artifact. Empty means
    engine-implicit output whose producer is defined by the adapter."""

    optional: bool = False
    """True when the artifact appears only under specific configurations."""

    time_indexed: bool = False
    """True for time-indexed outputs that produce one file per write interval.
    ``path_pattern`` will typically contain ``{time}``."""

    def __post_init__(self) -> None:
        # Catch typos like {caseId} or {run_id} at construction so they never
        # be finalized. Expansion-time validation alone is
        # not enough: an agent may read path_pattern literally without ever
        # calling expand_path_pattern.
        _validate_path_pattern(self.path_pattern)


_PATH_PATTERN_PLACEHOLDER: Final[re.Pattern[str]] = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
_KNOWN_PATH_PLACEHOLDERS: Final[frozenset[str]] = frozenset({"case_id", "time"})


def _validate_path_pattern(pattern: str) -> None:
    """Raise ``ValueError`` if ``pattern`` contains any placeholder not in
    :data:`_KNOWN_PATH_PLACEHOLDERS`. Does not require values — this is shape
    validation, not expansion. Called from :class:`DataArtifact.__post_init__`
    so typos surface at construction rather than at expand-time."""
    for match in _PATH_PATTERN_PLACEHOLDER.finditer(pattern):
        name = match.group(1)
        if name not in _KNOWN_PATH_PLACEHOLDERS:
            raise ValueError(
                f"unknown placeholder {{{name}}} in path pattern {pattern!r}; "
                f"recognised placeholders are {sorted(_KNOWN_PATH_PLACEHOLDERS)}"
            )


def expand_path_pattern(
    pattern: str,
    *,
    case_id: str | None = None,
    time: str | None = None,
) -> str:
    """Substitute ``{case_id}`` and ``{time}`` placeholders in a path pattern.

    The set of recognised placeholders is closed (see
    :data:`_KNOWN_PATH_PLACEHOLDERS`). Encountering an unknown ``{foo}`` token
    raises ``ValueError`` so authors cannot silently introduce a third
    placeholder convention.

    Passing an unused keyword (e.g., ``time=`` when the pattern has no
    ``{time}``) is tolerated — callers compose artifacts uniformly and should
    not have to inspect every pattern before invoking the helper.
    """
    _validate_path_pattern(pattern)
    values = {"case_id": case_id, "time": time}

    def _resolve(match: re.Match[str]) -> str:
        name = match.group(1)
        value = values[name]
        if value is None:
            raise ValueError(
                f"path pattern {pattern!r} references {{{name}}} but no "
                f"{name}= was supplied"
            )
        return value

    return _PATH_PATTERN_PLACEHOLDER.sub(_resolve, pattern)


def data_artifact_from_json(data: dict[str, Any]) -> DataArtifact:
    """Reconstruct a :class:`DataArtifact` from its JSON dict form.

    Inverse of ``dataclasses.asdict(artifact)``. ``variables`` is coerced
    back to a tuple of strings; absent optional keys fall back to the
    dataclass defaults. ``DataArtifact.__post_init__`` still runs, so a
    malformed ``path_pattern`` (unknown placeholder) raises ``ValueError``
    here rather than reaching the executor.
    """
    return DataArtifact(
        artifact_id=str(data["artifact_id"]),
        path_pattern=str(data["path_pattern"]),
        format=str(data["format"]),
        variables=tuple(str(v) for v in data.get("variables", ())),
        description=str(data.get("description", "")),
        produced_by=str(data.get("produced_by", "")),
        optional=bool(data.get("optional", False)),
        time_indexed=bool(data.get("time_indexed", False)),
    )


@dataclass(frozen=True)
class CaseConfig:
    """A single simulation configuration inside a tutorial sweep."""

    case_id: str
    params: dict[str, Any]


BuildCasesFn = Callable[[], list[CaseConfig]]
ApplyCaseFn = Callable[[Path, CaseConfig], None]

#: Phase 2 Task 10 (docs/superpowers/plans/2026-09-20-phase2-one-write-channel.md):
#: same two positional arguments as ``ApplyCaseFn``, but a spec that supplies
#: this is expected to have routed its mutation through the case-write
#: channel (``core.case_write``/``core.case_transaction``), and to say so by
#: returning the ``CaseWriteRecord`` that produced (``None`` only when the
#: mutation had nothing to write -- see ``apply_input_overrides_planned``'s
#: own docstring for that case). A spec with no case inputs to plan simply
#: does not need this field at all; it is optional, not a requirement every
#: spec must satisfy.
PlanCaseFn = Callable[[Path, CaseConfig], Any]


@dataclass(frozen=True)
class TutorialSpec:
    """Full tutorial definition consumed by the driver engine."""

    name: str
    case_root: Path
    setup_root: Path
    output_dir: Path
    build_cases: BuildCasesFn
    apply_case: ApplyCaseFn
    #: Preferred over ``apply_case`` when present (see ``invoke_case_mutation``
    #: below). ``None`` for every spec not yet migrated onto the case-write
    #: channel -- most of them, as of Task 10's first batch (2026-09-23): see
    #: that task's filled-in plan section for the exact count and which specs
    #: this covers.
    plan_case: PlanCaseFn | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def invoke_case_mutation(spec: "TutorialSpec", case_root: Path, case: CaseConfig) -> Any:
    """Apply one case's mutation, preferring the channel-routed path.

    Phase 2 Task 10. There is exactly one production call site for this
    today (``core.runtime.sweep_runner._materialize_entry_case``) -- see the
    plan's filled-in Task 10 section for the grep that established that.
    Centralized here rather than inlined at that call site so a future
    second call site gets the same preference-and-deprecation policy for
    free, instead of a second place that could drift from it.

    Falls back to ``apply_case`` with a ``DeprecationWarning`` naming the
    exact removal condition (Task 10: "removed when no in-tree spec supplies
    apply_case") rather than silently preferring one path forever -- a
    fallback with no stated removal condition is a fallback nobody is ever
    wrong to leave in place.
    """
    if spec.plan_case is not None:
        return spec.plan_case(case_root, case)
    import warnings

    warnings.warn(
        f"TutorialSpec {spec.name!r} supplies apply_case but not plan_case; "
        f"apply_case does not report what it wrote through the case-write "
        f"channel (if anything). This fallback is removed when no in-tree "
        f"spec supplies apply_case any more.",
        DeprecationWarning,
        stacklevel=2,
    )
    spec.apply_case(case_root, case)
    return None
