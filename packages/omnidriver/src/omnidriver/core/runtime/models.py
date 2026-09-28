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
    ``{case_id}`` (the sweep case identifier) and ``{instance}`` (one of the
    environment's declared instance directories; for OpenFOAM, a time
    directory). Anything else is a literal path component.
    """

    artifact_id: str
    """Stable identifier within the manifest. Predictor merges static + derived
    artifacts by ``artifact_id`` (static wins on collision)."""

    path_pattern: str
    """Case-relative path; may contain ``{case_id}`` / ``{instance}`` placeholders."""

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

    instance_indexed: bool = False
    """True for an output written once per solver-declared instance (for
    OpenFOAM, a time directory). ``path_pattern`` then contains
    ``{instance}``, which reconciliation substitutes with each name the
    environment's ``CaseRuntimeConventions.instance_directory_pattern``
    matches. Renamed from ``time_indexed`` 2026-09-26 (spec
    2026-09-26-core-generality-design.md §2, A2).

    Corrected 2026-09-26 (R2 fix, finding M2): said "each directory" the
    pattern matches, and by implication only at the case root. The pattern
    is matched against a name at every depth in the case tree, and applies
    to files too, not only directories -- see
    ``CaseRuntimeConventions.instance_directory_pattern``'s own docstring
    for the same correction in full."""

    def __post_init__(self) -> None:
        # Catch typos like {caseId} or {run_id} at construction so they never
        # be finalized. Expansion-time validation alone is
        # not enough: an agent may read path_pattern literally without ever
        # calling expand_path_pattern.
        _validate_path_pattern(self.path_pattern)


_PATH_PATTERN_PLACEHOLDER: Final[re.Pattern[str]] = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
_KNOWN_PATH_PLACEHOLDERS: Final[frozenset[str]] = frozenset({"case_id", "instance"})


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
    instance: str | None = None,
) -> str:
    """Substitute ``{case_id}`` and ``{instance}`` placeholders in a path pattern.

    The set of recognised placeholders is closed (see
    :data:`_KNOWN_PATH_PLACEHOLDERS`). Encountering an unknown ``{foo}`` token
    raises ``ValueError`` so authors cannot silently introduce a third
    placeholder convention.

    Passing an unused keyword (e.g., ``instance=`` when the pattern has no
    ``{instance}``) is tolerated — callers compose artifacts uniformly and
    should not have to inspect every pattern before invoking the helper.
    """
    _validate_path_pattern(pattern)
    values = {"case_id": case_id, "instance": instance}

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


#: Exactly the JSON keys :class:`DataArtifact` reconstructs from -- the same
#: closed set ``schemas/run-document.json``'s artifact object declares via
#: ``additionalProperties: false``. Named once, generically, rather than as
#: a hardcoded old-key comparison (R2 fix, finding M1): a renamed or removed
#: field (any of them, not only the A2 rename this was written for) is then
#: refused by name -- the actual key found, read back from the caller's own
#: data -- without core's source needing to spell any one specific retired
#: field name as a literal (scripts/check-core-shape.py's token scan is
#: about coupling to a *shape*, not about a caller's data mentioning one).
_ARTIFACT_JSON_KEYS: Final[frozenset[str]] = frozenset({
    "artifact_id", "path_pattern", "format", "variables", "description",
    "produced_by", "optional", "instance_indexed",
})


def data_artifact_from_json(data: dict[str, Any]) -> DataArtifact:
    """Reconstruct a :class:`DataArtifact` from its JSON dict form.

    Inverse of ``dataclasses.asdict(artifact)``. ``variables`` is coerced
    back to a tuple of strings; absent optional keys fall back to the
    dataclass defaults. ``DataArtifact.__post_init__`` still runs, so a
    malformed ``path_pattern`` (unknown placeholder) raises ``ValueError``
    here rather than reaching the executor.

    An unrecognised key -- a pre-A2 artifact's now-renamed field among them
    -- is refused by name (R2 fix, finding M1), never silently dropped:
    ``load_run_document`` schema-validates and already refuses one (the
    schema's ``additionalProperties: false``), but
    ``core.quantities.comparison._artifact`` reads a run document as raw
    JSON, with no schema validation -- that path used to accept an artifact
    carrying an old key and silently discard it via ``data.get(...)``,
    dropping the fact rather than refusing it.
    """
    unrecognised = sorted(set(data) - _ARTIFACT_JSON_KEYS)
    if unrecognised:
        raise ValueError(
            f"expectedArtifacts entry {data.get('artifact_id')!r} carries "
            f"unrecognised key(s) {unrecognised!r}; a renamed or removed "
            f"field (e.g. A2's instance_indexed rename, 2026-09-26) is "
            f"refused, never silently dropped or translated"
        )
    return DataArtifact(
        artifact_id=str(data["artifact_id"]),
        path_pattern=str(data["path_pattern"]),
        format=str(data["format"]),
        variables=tuple(str(v) for v in data.get("variables", ())),
        description=str(data.get("description", "")),
        produced_by=str(data.get("produced_by", "")),
        optional=bool(data.get("optional", False)),
        instance_indexed=bool(data.get("instance_indexed", False)),
    )


CaseMutationFn = Callable[[Path], Any]


@dataclass(frozen=True)
class TutorialSpec:
    """Full tutorial definition consumed by the driver engine.

    Step S6 (docs/superpowers/specs/2026-09-28-supplied-inputs-design.md):
    shrunk to exactly what a case folder (``core.runtime.generic_case``) and
    a tutorial record (``core.runtime.record_execution``) both actually
    build -- the two remaining spec constructors, now that every factory
    tutorial is gone (S5 deleted cardiacCore's, the last holdout). Dropped:
    ``setup_root``/``output_dir`` (now ``metadata["setup_root"]``/
    ``metadata["output_dir"]`` -- both builders already stashed comparable
    strings in ``metadata``, e.g. ``run_script_relpath``), and
    ``build_cases``/``apply_case``/``plan_case`` (a factory-tutorial spec
    could build MULTIPLE ``CaseConfig``s from one spec -- a parameter sweep
    baked into the factory itself; with no factory left, a spec is always
    exactly one case, so ``case_mutation`` replaces all three: one optional
    callable, called once, against the staged case root, returning whatever
    ``CaseWriteRecord`` (or ``None``) it wrote -- no case-count check, no
    deprecated non-reporting fallback, because there is no second authoring
    style left to prefer between).
    """

    name: str
    case_root: Path
    #: Optional: ``None`` when the spec mutates nothing (a marker-less
    #: generic case folder with no adapter-supplied callback, or a tutorial
    #: record, whose commit-time patches already happened before this spec
    #: was ever built -- see ``record_execution.commit_record_case``).
    #: Called with the staged case root only, once, by whichever caller
    #: stages it (``sweep_runner._materialize_entry_case``,
    #: ``introspection._resolve_proposed_changes``) -- never against
    #: ``spec.case_root`` itself.
    case_mutation: CaseMutationFn | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
