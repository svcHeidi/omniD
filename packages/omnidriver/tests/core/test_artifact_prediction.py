from __future__ import annotations

from pathlib import Path

from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.runtime.artifacts import predict_data_artifacts
from omnidriver.core.runtime.models import DataArtifact, TutorialSpec
from omnidriver.core.utility_catalog import ProducesEntry, UtilityManifest
from plugins.minimal_plugin import MinimalTestPlugin

_MANIFEST = UtilityManifest(
    name="makeField",
    description="",
    purpose="",
    inputs=(),
    requires_mesh=False,
    flags=(),
    example="",
    category="field",
    source_path=Path("makeField.toml"),
    produces=(ProducesEntry(artifact_id="field_out", path_pattern="0/field", format="text"),),
)


class _PluginWithUtility(MinimalTestPlugin):
    def get_utility_manifests(self) -> dict:
        return {"makeField": _MANIFEST}


def _spec(case_root: Path, **metadata: object) -> TutorialSpec:
    return TutorialSpec(
        name="fixture",
        case_root=case_root,
        metadata={"output_dir": str(case_root / "output"), **metadata},
    )


def _predict(case_root: Path, spec: TutorialSpec) -> dict[str, DataArtifact]:
    context = driver_context(_PluginWithUtility(), source="test:artifacts")
    return {a.artifact_id: a for a in predict_data_artifacts(case_root, spec, driver_context=context)}


def test_every_run_predicts_the_drivers_own_records(tmp_path: Path) -> None:
    artifacts = _predict(tmp_path, _spec(tmp_path))
    assert artifacts["core.workflow_state"].path_pattern == "output/workflow_state.json"
    assert artifacts["core.workflow_logs"].optional


def test_an_output_dir_outside_the_case_predicts_no_driver_records(tmp_path: Path) -> None:
    spec = TutorialSpec(
        name="fixture", case_root=tmp_path / "case",
        metadata={"output_dir": str(tmp_path / "elsewhere")},
    )
    assert _predict(tmp_path / "case", spec) == {}


def test_a_static_artifact_wins_on_an_id_collision(tmp_path: Path) -> None:
    override = DataArtifact(
        artifact_id="core.workflow_state", path_pattern="custom/path",
        format="csv_probe", description="hand-authored",
    )
    extra = DataArtifact(artifact_id="exact_error", path_pattern="exact.json", format="json_summary")
    artifacts = _predict(tmp_path, _spec(tmp_path, expected_artifacts=(override, extra)))
    assert artifacts["core.workflow_state"].path_pattern == "custom/path"
    assert "exact_error" in artifacts


def test_a_dag_step_naming_a_plugin_utility_contributes_its_produces(tmp_path: Path) -> None:
    dag = {"steps": [
        {"id": "mesh", "command": "blockMesh", "depends_on": []},
        {"id": "field", "command": "makeField", "depends_on": ["mesh"]},
    ]}
    artifacts = _predict(tmp_path, _spec(tmp_path, workflow_dag=dag))
    assert artifacts["field_out"].produced_by == "makeField"
    assert not [a for a in artifacts.values() if a.produced_by == "blockMesh"]
