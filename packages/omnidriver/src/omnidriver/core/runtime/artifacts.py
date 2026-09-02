"""Predict the data artifacts a tutorial run will (or did) produce.

The predictor is the single agent-facing answer to "what raw data does this
case produce?". It is consumed by the engine (to write
``workflow_state.json``) and by agents
exploring a case ahead of a real run.

Design discipline (plan v2 section 3):

* **Compose, do not branch.** Solver-aware logic SHOULD live in existing
  catalogs; the predictor reads them rather than reimplementing branching.
  Today the predictor actively consumes
  ``ionic_model_catalog.IONIC_MODEL_CATALOG`` (state + algebraic variables),
  ``omnidriver.cardiacfoam.detection.detect_ionic_export_list`` (user-declared
  exports),
  ``active_tension_catalog.ACTIVE_TENSION_MODEL_CATALOG`` (AT state variables,
  fired when ``activeTensionModel`` block is present), and
  the active plugin's utility manifests via the command-authorization
  capability (``produces`` of pre/post-solve utilities declared in
  ``workflow_dag`` steps).

* **Never raise on shape divergence.** Agents may call the predictor before
  ``apply_case`` has run, or against a partly-mutated case. Missing files,
  unknown solver names, and unknown ionic models all degrade to "return
  what we know" rather than throwing.
* **Static override wins.** A tutorial that knows it produces something the
  predictor cannot derive (e.g. analytic error norms for a manufactured
  solution) declares it via ``spec.metadata['expected_artifacts']``; on
  ``artifact_id`` collision the static entry replaces the derived one.

Adding a new solver means: write a ``_predict_<solver>`` handler and register
it in :data:`_SOLVER_HANDLERS`. Nothing else in this module branches on the
solver name.
"""
from __future__ import annotations

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
    """Translate a utility manifest's ProducesEntry into a DataArtifact.

    `produced_by` defaults to the utility name when the manifest leaves
    it blank — agents need to attribute the artifact regardless.
    """
    return DataArtifact(
        artifact_id=entry.artifact_id,
        path_pattern=entry.path_pattern,
        format=entry.format,
        variables=entry.variables,
        description=entry.description,
        produced_by=entry.produced_by or utility_name,
        optional=entry.optional,
        time_indexed=entry.time_indexed,
    )


def _predict_from_workflow_utilities(
    spec: TutorialSpec,
    driver_context: "DriverContext",
) -> tuple[DataArtifact, ...]:
    """Walk spec.metadata['workflow_dag'].steps; for each step whose
    `command` matches one of the active plugin's utility manifests, emit its
    `produces` entries as DataArtifacts.

    Returns ``()`` when the spec has no workflow_dag, no steps, or no
    matching utility commands. Unknown command names (e.g. OpenFOAM
    built-ins like ``blockMesh``) are silently skipped.
    """
    dag = spec.metadata.get("workflow_dag") if spec.metadata else None
    if not dag:
        return ()
    steps = dag.get("steps", ())
    if not steps:
        return ()
    utilities = driver_context.capabilities.command_authorization.utility_manifests()
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
    """The spec's output directory, as a case-relative POSIX prefix.

    ``path_pattern`` is case-relative (see ``models.DataArtifact``), and core
    writes its own state and logs under ``spec.output_dir`` -- never under a
    fixed ``postProcessing/``. Those two facts were previously connected by a
    string literal, so overriding ``output_dir_name`` moved the files and left
    the prediction behind.

    ``resolve_spec_paths`` builds ``output_dir`` as ``case_root / name``, so
    the relative form normally exists. An absolute ``output_dir_name`` escapes
    the case root; there is no case-relative pattern for that, so predict
    nothing rather than predict a wrong path.
    """
    try:
        return Path(spec.output_dir).relative_to(Path(spec.case_root)).as_posix()
    except ValueError:
        return ""


def _core_generic_artifacts(spec: TutorialSpec) -> tuple[DataArtifact, ...]:
    """Artifacts guaranteed by the driver for a generic case-folder run."""

    if not (spec.metadata or {}).get("generic_case"):
        return ()
    prefix = _output_dir_prefix(spec)
    if not prefix:
        return ()
    return (
        DataArtifact(
            artifact_id="core.workflow_state",
            path_pattern=f"{prefix}/workflow_state.json",
            format="json_summary",
            description="Persistent state of the normalized driverFOAM workflow.",
            produced_by="driverFOAM",
        ),
        DataArtifact(
            artifact_id="core.workflow_logs",
            path_pattern=f"{prefix}/workflow_logs",
            format="log",
            description="Per-step stdout and stderr logs written by driverFOAM.",
            produced_by="driverFOAM",
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

    Composes:

    * the static ``spec.metadata['expected_artifacts']`` override (if any),
    * solver-specific derivations driven by ``constant/electroProperties``,
      sourced from the ionic-model and active-tension catalogs.

    Never raises. Returns ``()`` when nothing can be derived and no static
    override is supplied.
    """
    from omnidriver.core.plugin_capabilities import ArtifactPredictionRequest

    static_override = spec.metadata.get("expected_artifacts", ()) if spec.metadata else ()
    static_tuple = tuple(static_override)

    plugin_derived = driver_context.capabilities.artifacts.predict(
        ArtifactPredictionRequest(case_root=case_root, spec=spec),
    )
    utility_derived = _predict_from_workflow_utilities(spec, driver_context)
    
    derived = _core_generic_artifacts(spec) + plugin_derived + utility_derived
    
    return _merge_static_override(derived, static_tuple)
