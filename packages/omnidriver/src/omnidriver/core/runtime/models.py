from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final


ArtifactFormat = str
"""Artifact output format. Open-ended by design, not a closed enum: most
format strings in practice are a solver plugin's own vocabulary for its own
outputs -- core has no business validating spellings it does not own (see
``future/ENVIRONMENT_CONTRACT.md`` §10). ``CORE_ARTIFACT_FORMATS`` below
names the only two values core itself ever writes, for its own artifacts."""

CORE_ARTIFACT_FORMATS: Final[frozenset[str]] = frozenset({"json_summary", "log"})
"""Format values used by artifacts core predicts for itself (see
``runtime/artifacts.py``'s core artifacts) -- not a validation gate
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
    matches -- against a name at any depth in the case tree, files
    included, not only directories at the case root."""

    def __post_init__(self) -> None:
        # Catch typos like {caseId} or {run_id} at construction so they never
        # be finalized. Expansion-time validation alone is
        # not enough: an agent may read path_pattern literally without ever
        # calling expand_path_pattern.
        _validate_path_pattern(self.path_pattern)


_PATH_PATTERN_PLACEHOLDER: Final[re.Pattern[str]] = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
_KNOWN_PATH_PLACEHOLDERS: Final[frozenset[str]] = frozenset({"case_id", "instance"})


def _validate_path_pattern(pattern: str) -> None:
    """Raise ``ValueError`` for a placeholder not in ``_KNOWN_PATH_PLACEHOLDERS``; shape only, no expansion."""
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
#: ``additionalProperties: false``. A renamed or removed field is then
#: refused by name -- the actual key found, read back from the caller's own
#: data -- rather than silently dropped.
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

    An unrecognised key is refused by name, never silently dropped:
    ``core.quantities.comparison._artifact`` reads a run document as raw
    JSON with no schema validation, so this is the one place that catches an
    unknown field on that path.
    """
    unrecognised = sorted(set(data) - _ARTIFACT_JSON_KEYS)
    if unrecognised:
        raise ValueError(
            f"expectedArtifacts entry {data.get('artifact_id')!r} carries "
            f"unrecognised key(s) {unrecognised!r}; an unknown field is "
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


@dataclass(frozen=True)
class TutorialSpec:
    """One committed record case: its name, staged root and planning metadata.

    Built only by ``core.runtime.record_execution.record_case_spec``.
    """

    name: str
    case_root: Path
    metadata: dict[str, Any] = field(default_factory=dict)
