"""Predict the data artifacts a tutorial run will (or did) produce; never raises.

Composes the adapter's artifact declarations with any static ``spec.metadata['expected_artifacts']``."""
from __future__ import annotations

#: produced_by for files the executor itself writes, not the solver command.
DRIVER_PRODUCED_BY = "omnidriver"

from pathlib import Path
from typing import TYPE_CHECKING, Callable, Iterable

from omnidriver.core.utility_catalog import ProducesEntry
from .models import DataArtifact, TutorialSpec

if TYPE_CHECKING:
    from ..plugin_interface import DriverContext




def _produces_entry_to_artifact(
    entry: "ProducesEntry",
    utility_name: str,
) -> DataArtifact:
    """Translate a utility manifest's ProducesEntry into a DataArtifact; produced_by defaults to the utility name when blank."""
    return DataArtifact(
        artifact_id=entry.artifact_id,
        path_pattern=entry.path_pattern,
        format=entry.format,
        variables=entry.variables,
        description=entry.description,
        produced_by=entry.produced_by or utility_name,
        optional=entry.optional,
        instance_indexed=entry.instance_indexed,
    )


def _predict_from_workflow_utilities(
    spec: TutorialSpec,
    driver_context: "DriverContext",
) -> tuple[DataArtifact, ...]:
    """Emit DataArtifacts from each workflow_dag step whose command matches an active plugin utility manifest."""
    dag = spec.metadata.get("workflow_dag") if spec.metadata else None
    if not dag:
        return ()
    steps = dag.get("steps", ())
    if not steps:
        return ()
    utilities = driver_context.stack.call("get_utility_manifests")
    derived: list[DataArtifact] = []
    for step in steps:
        command = step.get("command")
        if not command or command not in utilities:
            continue
        manifest = utilities[command]
        for produce in manifest.produces:
            derived.append(_produces_entry_to_artifact(produce, command))
    return tuple(derived)


def _merge_static_override(
    derived: tuple[DataArtifact, ...],
    static: Iterable[DataArtifact],
) -> tuple[DataArtifact, ...]:
    by_id: dict[str, DataArtifact] = {a.artifact_id: a for a in derived}
    for override in static:
        by_id[override.artifact_id] = override
    return tuple(by_id.values())


def _output_dir_prefix(spec: TutorialSpec) -> str:
    """The output directory as a case-relative POSIX prefix; empty when it escapes the case root."""
    try:
        return Path(spec.metadata["output_dir"]).relative_to(Path(spec.case_root)).as_posix()
    except (ValueError, KeyError):
        return ""


def _core_artifacts(spec: TutorialSpec) -> tuple[DataArtifact, ...]:
    """Artifacts the driver itself writes for every run."""
    prefix = _output_dir_prefix(spec)
    if not prefix:
        return ()
    return (
        DataArtifact(
            artifact_id="core.workflow_state",
            path_pattern=f"{prefix}/workflow_state.json",
            format="json_summary",
            description="Persistent state of the normalized omnidriver workflow.",
            produced_by=DRIVER_PRODUCED_BY,
        ),
        DataArtifact(
            artifact_id="core.workflow_logs",
            path_pattern=f"{prefix}/workflow_logs",
            format="log",
            description="Per-step stdout and stderr logs written by omnidriver.",
            produced_by=DRIVER_PRODUCED_BY,
            optional=True,
        ),
    )


def predict_data_artifacts(
    case_root: Path,
    spec: TutorialSpec,
    *,
    driver_context: "DriverContext",
) -> tuple[DataArtifact, ...]:
    """Return the artifacts ``case_root`` will (or does) produce.

    Composes adapter-derived artifacts with any static
    ``spec.metadata['expected_artifacts']`` override. Never raises;
    returns ``()`` when nothing can be derived.
    """
    static_override = spec.metadata.get("expected_artifacts", ()) if spec.metadata else ()
    static_tuple = tuple(static_override)

    plugin_derived = driver_context.stack.call("predict_data_artifacts", case_root, spec)
    utility_derived = _predict_from_workflow_utilities(spec, driver_context)
    
    derived = _core_artifacts(spec) + plugin_derived + utility_derived
    
    return _merge_static_override(derived, static_tuple)
