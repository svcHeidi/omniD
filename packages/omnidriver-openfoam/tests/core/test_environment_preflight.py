"""Environment preflight gate tests.

Every test monkeypatches shutil.which / os.environ instead of touching the machine.
"""

import shutil

import pytest

from omnidriver.openfoam.openfoam_environment import load_openfoam_environment
from omnidriver.core.plugin_interface import load_plugin_context
from omnidriver.openfoam.environment_preflight import (
    _environment_diagnostics,
    _required_executables,
)
from omnidriver.core.strict_planning import (
    StrictDiagnostic,
    StrictPlanReport,
)


def _dag(*commands):
    """Build a workflow_dag dict. Each entry is a str command or (command, args)."""
    steps = []
    for entry in commands:
        if isinstance(entry, tuple):
            command, args = entry
        else:
            command, args = entry, []
        steps.append({"command": command, "args": list(args)})
    return {"steps": steps}


def _which_factory(present):
    present = set(present)

    def fake_which(name, *args, **kwargs):
        return f"/usr/bin/{name}" if name in present else None

    return fake_which


def _diags(workflow_dag, driver_context=None):
    import os

    return _environment_diagnostics(
        workflow_dag, env=dict(os.environ), driver_context=driver_context,
    )


def test_required_executables_collects_step_commands():
    reqs = _required_executables(_dag("blockMesh", "cardiacFoam", "setExprFields"))
    assert reqs.executables == ("blockMesh", "cardiacFoam", "setExprFields")
    assert reqs.is_parallel is False
    assert reqs.mpi_launcher_in_dag is False


def test_required_executables_dedupes():
    reqs = _required_executables(_dag("python3", "cardiacFoam", "cardiacFoam"))
    assert reqs.executables == ("python3", "cardiacFoam")


def test_required_executables_unwraps_mpi_launcher():
    reqs = _required_executables(
        _dag(("mpirun", ["-np", "4", "cardiacFoam", "-parallel"]))
    )
    assert reqs.executables == ("mpirun", "cardiacFoam")
    assert reqs.is_parallel is True
    assert reqs.mpi_launcher_in_dag is True


def test_required_executables_parallel_via_flag_or_decompose():
    via_flag = _required_executables(_dag(("cardiacFoam", ["-parallel"])))
    assert via_flag.is_parallel is True
    assert via_flag.mpi_launcher_in_dag is False

    via_decompose = _required_executables(_dag("decomposePar", "cardiacFoam"))
    assert via_decompose.is_parallel is True


def test_required_executables_none_dag_is_empty():
    reqs = _required_executables(None)
    assert reqs.executables == ()
    assert reqs.is_parallel is False


@pytest.fixture
def clean_env(monkeypatch):
    """A fully-sourced OpenFOAM env with the preflight gate enabled."""
    monkeypatch.setenv("WM_PROJECT_DIR", "/opt/openfoam")
    monkeypatch.setenv("WM_PROJECT_VERSION", "v2406")
    monkeypatch.setenv("FOAM_USER_LIBBIN", "/home/u/platforms/lib")
    return monkeypatch


def test_a_program_not_on_path_is_an_error_naming_it(clean_env):
    clean_env.setattr(
        shutil, "which", _which_factory({"blockMesh", "cardiacFoam"})
    )
    diags = _diags(_dag("blockMesh", "cardiacFoam", "setExprFields"))
    missing = [d for d in diags if d.code == "program_not_on_path"]
    assert len(missing) == 1
    assert missing[0].level == "error"
    assert missing[0].field == "setExprFields"


def test_present_executables_have_no_error(clean_env):
    clean_env.setattr(
        shutil, "which", _which_factory({"blockMesh", "cardiacFoam"})
    )
    diags = _diags(_dag("blockMesh", "cardiacFoam"))
    assert "program_not_on_path" not in {d.code for d in diags}


def test_case_script_commands_are_not_path_checked(clean_env):
    # Allrun/Allclean/etc are case-local scripts resolved relative to
    # caseRoot at execution time, never on PATH by design.
    clean_env.setattr(shutil, "which", _which_factory(set()))
    diags = _diags(_dag("Allrun"), load_plugin_context("openfoam-environment"))
    assert "program_not_on_path" not in {d.code for d in diags}


def _fake_context_declaring_entrypoint(relpath: str):
    """A minimal stand-in exposing only the runtime convention declaration."""
    from types import SimpleNamespace

    from omnidriver.core.plugin_interface import CaseRuntimeConventions

    conventions = CaseRuntimeConventions(
        case_entrypoints=(relpath,), case_script_commands=(relpath,),
    )
    return SimpleNamespace(stack=SimpleNamespace(call=lambda member: conventions))


def test_a_declared_entrypoint_is_also_not_path_checked():
    reqs_no_context = _required_executables(_dag("run.sh"))
    assert "run.sh" in reqs_no_context.executables

    ctx = _fake_context_declaring_entrypoint("run.sh")
    reqs_with_context = _required_executables(_dag("run.sh"), ctx)
    assert "run.sh" not in reqs_with_context.executables


def test_a_declared_case_script_given_as_a_path_from_the_case_is_not_path_checked():
    """A step names a case script by ``./<path>``, as core's allowlist accepts it; an undeclared one is still looked for."""
    ctx = _fake_context_declaring_entrypoint("setup/extract_cv.py")
    reqs = _required_executables(_dag("./setup/extract_cv.py", "./setup/other.py", "blockMesh"), ctx)
    assert reqs.executables == ("./setup/other.py", "blockMesh")


def test_mpi_wrapper_checks_launcher_and_program(clean_env):
    clean_env.setattr(shutil, "which", _which_factory({"mpirun"}))
    diags = _diags(
        _dag(("mpirun", ["-np", "4", "cardiacFoam", "-parallel"]))
    )
    missing = {d.field for d in diags if d.code == "program_not_on_path"}
    assert missing == {"cardiacFoam"}  # mpirun present, cardiacFoam missing
    assert "missing_mpi" not in {d.code for d in diags}  # launcher is in the dag


def test_parallel_without_launcher_reports_missing_mpi(clean_env):
    clean_env.setattr(shutil, "which", _which_factory({"cardiacFoam"}))
    diags = _diags(_dag(("cardiacFoam", ["-parallel"])))
    assert "missing_mpi" in {d.code for d in diags}


def test_serial_plan_has_no_mpi_error(clean_env):
    clean_env.setattr(shutil, "which", _which_factory({"cardiacFoam"}))
    diags = _diags(_dag("cardiacFoam"))
    assert "missing_mpi" not in {d.code for d in diags}


def test_missing_wm_project_dir_is_error(clean_env):
    clean_env.delenv("WM_PROJECT_DIR", raising=False)
    clean_env.setattr(shutil, "which", _which_factory({"cardiacFoam"}))
    diags = _diags(_dag("cardiacFoam"))
    errors = [d for d in diags if d.code == "missing_openfoam_env"]
    assert len(errors) == 1
    assert errors[0].level == "error"


def test_partial_openfoam_env_is_warning_only(clean_env):
    clean_env.delenv("WM_PROJECT_VERSION", raising=False)
    clean_env.setattr(shutil, "which", _which_factory({"cardiacFoam"}))
    diags = _diags(_dag("cardiacFoam"))
    partial = [d for d in diags if d.code == "partial_openfoam_env"]
    assert len(partial) == 1
    assert partial[0].level == "warning"
    assert partial[0].field == "WM_PROJECT_VERSION"


def test_both_partial_env_vars_missing_yield_two_warnings(clean_env):
    clean_env.delenv("WM_PROJECT_VERSION", raising=False)
    clean_env.delenv("FOAM_USER_LIBBIN", raising=False)
    clean_env.setattr(shutil, "which", _which_factory({"cardiacFoam"}))
    diags = _diags(_dag("cardiacFoam"))
    partial = {d.field for d in diags if d.code == "partial_openfoam_env"}
    assert partial == {"WM_PROJECT_VERSION", "FOAM_USER_LIBBIN"}


def test_no_partial_warnings_when_openfoam_unsourced(clean_env):
    clean_env.delenv("WM_PROJECT_DIR", raising=False)
    clean_env.delenv("WM_PROJECT_VERSION", raising=False)
    clean_env.delenv("FOAM_USER_LIBBIN", raising=False)
    clean_env.setattr(shutil, "which", _which_factory({"cardiacFoam"}))
    diags = _diags(_dag("cardiacFoam"))
    codes = {d.code for d in diags}
    assert "missing_openfoam_env" in codes
    assert "partial_openfoam_env" not in codes


def test_load_openfoam_environment_sources_bashrc(tmp_path, monkeypatch):
    bashrc = tmp_path / "bashrc"
    foam_bin = tmp_path / "bin"
    foam_bin.mkdir()
    (foam_bin / "cardiacFoam").write_text("#!/bin/sh\n")
    (foam_bin / "cardiacFoam").chmod(0o755)
    bashrc.write_text(
        f"export WM_PROJECT_DIR={tmp_path}\n"
        "export WM_PROJECT_VERSION=v2412\n"
        f"export FOAM_USER_LIBBIN={tmp_path / 'lib'}\n"
        f"export PATH={foam_bin}:$PATH\n"
    )

    loaded = load_openfoam_environment(bashrc_path=bashrc, base_env={})

    assert loaded.error is None
    assert loaded.env["WM_PROJECT_DIR"] == str(tmp_path)
    assert loaded.env["WM_PROJECT_VERSION"] == "v2412"
    diags = _environment_diagnostics(_dag("cardiacFoam"), env=loaded.env)
    assert not [d for d in diags if d.level == "error"]


def test_report_to_json_contains_environment_diagnostics():
    report = StrictPlanReport(
        status="ok",
        entry="singleCell",
        resolved_entry={},
        environment_diagnostics=(
            StrictDiagnostic(level="error", code="program_not_on_path",
                             message="x", source="environment", field="cardiacFoam"),
        ),
    )
    payload = report.to_json()
    assert "environment_diagnostics" in payload
    entry = payload["environment_diagnostics"][0]
    assert entry["field"] == "cardiacFoam"
    assert entry["level"] == "error"
    assert entry["code"] == "program_not_on_path"


def test_report_to_json_environment_diagnostics_defaults_empty():
    report = StrictPlanReport(status="ok", entry="singleCell", resolved_entry={})
    assert report.to_json()["environment_diagnostics"] == []


def test_unsourced_environment_does_not_block_a_plan_that_needs_no_openfoam(clean_env):
    clean_env.delenv("WM_PROJECT_DIR", raising=False)
    clean_env.setattr(shutil, "which", _which_factory(set()))

    diags = _diags({"steps": []})

    blocking = [d for d in diags if d.level == "error"]
    assert blocking == [], (
        "a plan that invokes no OpenFOAM executable is blocked because OpenFOAM "
        f"is not sourced: {[(d.code, d.message) for d in blocking]}"
    )


def test_an_unsourced_environment_is_still_reported_when_nothing_needs_it(clean_env):
    clean_env.delenv("WM_PROJECT_DIR", raising=False)
    clean_env.setattr(shutil, "which", _which_factory(set()))

    diags = _diags({"steps": []})

    assert [d for d in diags if d.code == "openfoam_env_not_sourced"], (
        "nothing records that the environment was unsourced: "
        f"{[(d.level, d.code) for d in diags]}"
    )



@pytest.mark.parametrize("version, mismatched", [
    ("mpirun (Open MPI) 5.0.9", False),
    ("HYDRA build details:\n    Version: 4.0.1", True),
])
def test_an_mpirun_from_another_mpi_family_is_refused(tmp_path, version, mismatched):
    """``WM_MPLIB`` names the family ``mpirun --version`` must print; a
    mismatch means the wrong MPI would silently run underneath."""
    from omnidriver.openfoam.environment_preflight import _mpi_family_diagnostics

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    launcher = bin_dir / "mpirun"
    launcher.write_text(f"#!/bin/sh\nprintf '%s\\n' '{version}'\n")
    launcher.chmod(0o755)
    env = {"PATH": str(bin_dir), "WM_MPLIB": "SYSTEMOPENMPI"}
    codes = [d.code for d in _mpi_family_diagnostics(env)]
    assert codes == (["openfoam_mpi_launcher_mismatch"] if mismatched else [])
    assert _mpi_family_diagnostics({**env, "WM_MPLIB": "SOMETHINGELSE"}) == ()


def test_the_bashrc_is_never_searched_for(tmp_path):
    from omnidriver.openfoam.openfoam_environment import openfoam_bashrc

    assert openfoam_bashrc(bashrc_path="/explicit", base_env={"OPENFOAM_BASHRC": "/env"}).as_posix() == "/explicit"
    assert openfoam_bashrc(base_env={"OPENFOAM_BASHRC": "/env"}).as_posix() == "/env"
    install = tmp_path / "install"
    (install / "etc").mkdir(parents=True)
    (install / "etc" / "bashrc").write_text("")
    assert openfoam_bashrc(base_env={"WM_PROJECT_DIR": str(install)}) == install / "etc" / "bashrc"
    assert openfoam_bashrc(base_env={"WM_PROJECT_DIR": str(tmp_path)}) is None
    assert openfoam_bashrc(base_env={}) is None


def test_a_supplied_bashrc_that_does_not_exist_is_refused_by_name(tmp_path):
    loaded = load_openfoam_environment(base_env={"OPENFOAM_BASHRC": str(tmp_path / "absent")})
    assert loaded.error == f"OpenFOAM bashrc not found: {tmp_path / 'absent'}"


def test_env_reports_the_bashrc_a_run_would_source_and_where_it_found_it(tmp_path):
    from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin
    from omnidriver.openfoam.openfoam_environment import openfoam_bashrc

    install = tmp_path / "install"
    (install / "etc").mkdir(parents=True)
    (install / "etc" / "bashrc").write_text("")
    plugin = OpenFOAMEnvironmentPlugin()
    sourced_shell = {"WM_PROJECT_DIR": str(install)}

    assert plugin.resolve_supplied_variables(sourced_shell) == {
        "OPENFOAM_BASHRC": {"value": str(install / "etc" / "bashrc"), "resolved_from": "WM_PROJECT_DIR"},
    }
    assert plugin.resolve_supplied_variables(sourced_shell)["OPENFOAM_BASHRC"]["value"] == str(
        openfoam_bashrc(base_env=sourced_shell),
    )
    assert plugin.resolve_supplied_variables({"OPENFOAM_BASHRC": "/named", **sourced_shell}) == {}
    assert plugin.resolve_supplied_variables({}) == {}


def test_the_openfoam_shell_keeps_the_bashrcs_library_path_in_front_of_dyld_library_path():
    from importlib import resources

    from omnidriver.core.environment_connection import render_prefix
    from omnidriver.core.plugin_profile import load_plugin_profile

    manifest = resources.files("omnidriver.openfoam") / "openfoam-environment.yaml"
    connection = load_plugin_profile(manifest).environment
    assert {variable.name: variable.keeps for variable in connection.supplied}["DYLD_LIBRARY_PATH"] == "FOAM_LD_LIBRARY_PATH"
    prefix = render_prefix(connection, {"OPENFOAM_BASHRC": "/of/etc/bashrc", "DYLD_LIBRARY_PATH": "/opt/lib"})
    assert prefix == (
        'source /of/etc/bashrc; export DYLD_LIBRARY_PATH="${FOAM_LD_LIBRARY_PATH:+$FOAM_LD_LIBRARY_PATH:}"/opt/lib; '
    )
