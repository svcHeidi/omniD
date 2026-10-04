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


def test_required_executables_skips_interpreters_and_dedupes():
    reqs = _required_executables(_dag("python3", "cardiacFoam", "cardiacFoam"))
    assert reqs.executables == ("cardiacFoam",)


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


def _make_exec(path):
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)


def test_build_staleness_warns_when_user_binary_older_than_source(tmp_path):
    import os

    from omnidriver.openfoam.environment_preflight import (
        _build_staleness_diagnostics,
    )

    src_root = tmp_path / "src"
    src_root.mkdir()
    source = src_root / "solver.C"
    source.write_text("// code")
    os.utime(source, (2000, 2000))  # source newer than the binary below

    appbin = tmp_path / "appbin"
    appbin.mkdir()
    _make_exec(appbin / "myFoam")
    os.utime(appbin / "myFoam", (1000, 1000))  # stale: older than source

    env = {"PATH": str(appbin), "FOAM_USER_APPBIN": str(appbin)}
    diags = _build_staleness_diagnostics(_dag("myFoam"), env, src_root=src_root)

    assert len(diags) == 1
    assert diags[0].level == "warning"
    assert diags[0].code == "stale_build"
    assert diags[0].field == "myFoam"


def test_build_staleness_silent_when_binary_newer_than_source(tmp_path):
    import os

    from omnidriver.openfoam.environment_preflight import (
        _build_staleness_diagnostics,
    )

    src_root = tmp_path / "src"
    src_root.mkdir()
    source = src_root / "solver.C"
    source.write_text("// code")
    os.utime(source, (1000, 1000))  # older than the binary

    appbin = tmp_path / "appbin"
    appbin.mkdir()
    _make_exec(appbin / "myFoam")
    os.utime(appbin / "myFoam", (2000, 2000))  # fresh

    env = {"PATH": str(appbin), "FOAM_USER_APPBIN": str(appbin)}
    diags = _build_staleness_diagnostics(_dag("myFoam"), env, src_root=src_root)
    assert diags == ()


def test_build_staleness_ignores_binaries_outside_user_appbin(tmp_path):
    import os

    from omnidriver.openfoam.environment_preflight import (
        _build_staleness_diagnostics,
    )

    src_root = tmp_path / "src"
    src_root.mkdir()
    source = src_root / "solver.C"
    source.write_text("// code")
    os.utime(source, (2000, 2000))

    sysbin = tmp_path / "sysbin"
    sysbin.mkdir()
    _make_exec(sysbin / "blockMesh")
    os.utime(sysbin / "blockMesh", (1000, 1000))  # older, but not user-compiled

    env = {"PATH": str(sysbin), "FOAM_USER_APPBIN": str(tmp_path / "appbin")}
    diags = _build_staleness_diagnostics(_dag("blockMesh"), env, src_root=src_root)
    assert diags == ()


def test_a_stale_build_names_the_binary_and_the_newest_source_file(tmp_path):
    import os

    from omnidriver.openfoam.environment_preflight import _build_staleness_diagnostics

    src_root = tmp_path / "src"
    (src_root / "models").mkdir(parents=True)
    for name, stamp in (("old.C", 1500), ("new.C", 3000), ("newer.H", 2000)):
        (src_root / "models" / name).write_text("// code")
        os.utime(src_root / "models" / name, (stamp, stamp))
    appbin = tmp_path / "appbin"
    appbin.mkdir()
    _make_exec(appbin / "myFoam")
    os.utime(appbin / "myFoam", (1000, 1000))

    env = {"PATH": str(appbin), "FOAM_USER_APPBIN": str(appbin)}
    (diagnostic,) = _build_staleness_diagnostics(_dag("myFoam"), env, src_root=src_root)
    for fragment in ("myFoam", str(appbin / "myFoam"), "3 source file(s)", "models/new.C", "a state this binary was not built from"):
        assert fragment in diagnostic.message, (fragment, diagnostic.message)


def test_a_library_a_make_files_builds_is_stale_against_its_own_sources_only(tmp_path):
    import os

    from omnidriver.openfoam.environment_preflight import _build_staleness_diagnostics

    src_root = tmp_path / "src"
    for directory, stamp in (("electroModels", 3000), ("ionicModels", 500)):
        (src_root / directory / "Make").mkdir(parents=True)
        (src_root / directory / "Make" / "files").write_text(
            f"model.C\n\nLIB = $(FOAM_USER_LIBBIN)/lib{directory}\n"
        )
        (src_root / directory / "model.C").write_text("// code")
        os.utime(src_root / directory / "model.C", (stamp, stamp))
    appbin, libbin = tmp_path / "appbin", tmp_path / "lib"
    appbin.mkdir()
    libbin.mkdir()
    _make_exec(appbin / "myFoam")
    os.utime(appbin / "myFoam", (4000, 4000))
    for directory in ("electroModels", "ionicModels"):
        (libbin / f"lib{directory}.dylib").write_text("lib")
        os.utime(libbin / f"lib{directory}.dylib", (1000, 1000))

    env = {"PATH": str(appbin), "FOAM_USER_APPBIN": str(appbin), "FOAM_USER_LIBBIN": str(libbin)}
    (diagnostic,) = _build_staleness_diagnostics(_dag("myFoam"), env, src_root=src_root)
    assert (diagnostic.code, diagnostic.field) == ("stale_build", "libelectroModels")
    assert "electroModels/model.C" in diagnostic.message


def test_build_staleness_no_src_root_is_silent(tmp_path):
    from omnidriver.openfoam.environment_preflight import (
        _build_staleness_diagnostics,
    )

    env = {"PATH": "", "FOAM_USER_APPBIN": str(tmp_path)}
    assert _build_staleness_diagnostics(_dag("myFoam"), env, src_root=None) == ()


@pytest.fixture
def clean_env(monkeypatch):
    """A fully-sourced OpenFOAM env with the preflight gate enabled."""
    monkeypatch.setenv("WM_PROJECT_DIR", "/opt/openfoam")
    monkeypatch.setenv("WM_PROJECT_VERSION", "v2406")
    monkeypatch.setenv("FOAM_USER_LIBBIN", "/home/u/platforms/lib")
    return monkeypatch


def test_missing_executable_is_error(clean_env):
    clean_env.setattr(
        shutil, "which", _which_factory({"blockMesh", "cardiacFoam"})
    )
    diags = _diags(_dag("blockMesh", "cardiacFoam", "setExprFields"))
    missing = [d for d in diags if d.code == "missing_executable"]
    assert len(missing) == 1
    assert missing[0].level == "error"
    assert missing[0].field == "setExprFields"
    # Conformance C9 requires the missing command as a quoted token.
    assert missing[0].message == "'setExprFields' not found on PATH."


def test_present_executables_have_no_error(clean_env):
    clean_env.setattr(
        shutil, "which", _which_factory({"blockMesh", "cardiacFoam"})
    )
    diags = _diags(_dag("blockMesh", "cardiacFoam"))
    assert "missing_executable" not in {d.code for d in diags}


def test_case_script_commands_are_not_path_checked(clean_env):
    # Allrun/Allclean/etc are case-local scripts resolved relative to
    # caseRoot at execution time, never on PATH by design.
    clean_env.setattr(shutil, "which", _which_factory(set()))
    diags = _diags(_dag("Allrun"), load_plugin_context("openfoam-environment"))
    assert "missing_executable" not in {d.code for d in diags}


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


def test_mpi_wrapper_checks_launcher_and_program(clean_env):
    clean_env.setattr(shutil, "which", _which_factory({"mpirun"}))
    diags = _diags(
        _dag(("mpirun", ["-np", "4", "cardiacFoam", "-parallel"]))
    )
    missing = {d.field for d in diags if d.code == "missing_executable"}
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
            StrictDiagnostic(level="error", code="missing_executable",
                             message="x", source="environment", field="cardiacFoam"),
        ),
    )
    payload = report.to_json()
    assert "environment_diagnostics" in payload
    entry = payload["environment_diagnostics"][0]
    assert entry["field"] == "cardiacFoam"
    assert entry["level"] == "error"
    assert entry["code"] == "missing_executable"


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



def test_the_stale_build_check_reads_the_supplied_source_root_only(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from omnidriver.core.plugin_profile import CxxMapping
    from omnidriver.openfoam.environment_preflight import _supplied_src_root

    mapping = CxxMapping("TOY_TREE", "src", tmp_path / "allowlist.json")
    context = SimpleNamespace(stack=SimpleNamespace(call=lambda member: SimpleNamespace(cxx_mapping=mapping)))
    monkeypatch.delenv("TOY_TREE", raising=False)
    assert _supplied_src_root(context) is None
    assert _supplied_src_root(None) is None
    monkeypatch.setenv("TOY_TREE", str(tmp_path))
    assert _supplied_src_root(context) == (tmp_path / "src").resolve()


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

    runtime_file = tmp_path / "runtime.yaml"
    runtime_file.write_text("openfoam:\n  bashrc: /from/runtime/file\n")
    named = {"OMNIDRIVER_RUNTIME_CONFIG": str(runtime_file)}

    assert openfoam_bashrc(bashrc_path="/explicit", base_env={**named, "OPENFOAM_BASHRC": "/env"}).as_posix() == "/explicit"
    assert openfoam_bashrc(base_env={**named, "OPENFOAM_BASHRC": "/env"}).as_posix() == "/env"
    assert openfoam_bashrc(base_env=named).as_posix() == "/from/runtime/file"
    install = tmp_path / "install"
    (install / "etc").mkdir(parents=True)
    (install / "etc" / "bashrc").write_text("")
    assert openfoam_bashrc(base_env={"WM_PROJECT_DIR": str(install)}) == install / "etc" / "bashrc"
    assert openfoam_bashrc(base_env={"WM_PROJECT_DIR": str(tmp_path)}) is None
    assert openfoam_bashrc(base_env={}) is None


def test_a_supplied_bashrc_that_does_not_exist_is_refused_by_name(tmp_path):
    loaded = load_openfoam_environment(base_env={"OPENFOAM_BASHRC": str(tmp_path / "absent")})
    assert loaded.error == f"OpenFOAM bashrc not found: {tmp_path / 'absent'}"


def test_env_reports_the_bashrc_a_run_would_source(tmp_path):
    from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin
    from omnidriver.openfoam.openfoam_environment import openfoam_bashrc

    install = tmp_path / "install"
    (install / "etc").mkdir(parents=True)
    (install / "etc" / "bashrc").write_text("")
    plugin = OpenFOAMEnvironmentPlugin()
    sourced_shell = {"WM_PROJECT_DIR": str(install)}

    assert plugin.resolve_supplied_variables(sourced_shell)["OPENFOAM_BASHRC"] == str(install / "etc" / "bashrc")
    assert plugin.resolve_supplied_variables(sourced_shell)["OPENFOAM_BASHRC"] == str(openfoam_bashrc(base_env=sourced_shell))
    assert plugin.resolve_supplied_variables({"OPENFOAM_BASHRC": "/named", **sourced_shell})["OPENFOAM_BASHRC"] == "/named"
    assert "OPENFOAM_BASHRC" not in plugin.resolve_supplied_variables({})
