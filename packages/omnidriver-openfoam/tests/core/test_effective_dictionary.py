"""Contract tests for explicit native effective dictionary resolution."""
from __future__ import annotations

import inspect
import os
import subprocess
from pathlib import Path

import pytest

from omnidriver.openfoam.effective_dictionary import (
    inspect_effective_foam_configuration,
    resolve_effective_foam_entry,
)
from omnidriver.openfoam.openfoam_environment import discover_openfoam_bashrc


HEADER = "FoamFile { version 2.0; format ascii; class dictionary; object d; }\n"
NATIVE_BASHRC = discover_openfoam_bashrc()
native = pytest.mark.skipif(
    NATIVE_BASHRC is None,
    reason="no OpenFOAM installation discoverable; native effective resolution is not verified",
)


def test_bashrc_default_is_not_a_hardcoded_machine_path():
    """The shipped default must not name one machine's absolute path."""
    sig = inspect.signature(resolve_effective_foam_entry)
    default = sig.parameters["bashrc"].default
    assert not isinstance(default, (str, Path)), (
        f"bashrc default is a hardcoded path: {default!r}; "
        "it must be a sentinel that triggers ambient discovery instead"
    )


def test_unspecified_bashrc_does_not_mask_lexical_execution_required(monkeypatch, tmp_path):
    """Purely-lexical classification needs no runtime and must not be
    shadowed by a runtime-availability gate when nothing is discoverable."""
    import omnidriver.openfoam.effective_dictionary as effective_dictionary_module

    monkeypatch.setattr(effective_dictionary_module, "discover_openfoam_bashrc", lambda: None)
    path = tmp_path / "d"
    path.write_text(
        HEADER + f'pwned #codeStream {{ code #{{ system("touch dummy"); #}}; }};\n'
    )

    result = effective_dictionary_module.resolve_effective_foam_entry(path, "pwned")

    assert result.status == "execution_required"


def test_missing_runtime_is_explicit_not_a_lexical_fallback(tmp_path: Path) -> None:
    path = tmp_path / "d"
    path.write_text(HEADER + "value 1;\n")
    result = resolve_effective_foam_entry(path, "value", bashrc=tmp_path / "missing-bashrc")
    assert result.status == "runtime_unavailable"
    assert result.value is None
    assert result.parser == "foamDictionary"


def test_configured_execution_environment_runs_native_parser_without_resourcing(
    monkeypatch, tmp_path: Path,
) -> None:
    path = tmp_path / "d"
    path.write_text(HEADER + "value 1;\n")
    executable = tmp_path / "foamDictionary"
    executable.write_text("")
    seen: dict = {}

    monkeypatch.setattr(
        "omnidriver.openfoam.effective_dictionary.shutil.which",
        lambda name, path: str(executable),
    )

    def fake_run(command, **kwargs):
        seen["command"] = command
        seen["env"] = kwargs["env"]
        return subprocess.CompletedProcess(command, 0, stdout="7\n", stderr="")

    monkeypatch.setattr(
        "omnidriver.openfoam.effective_dictionary.subprocess.run", fake_run,
    )
    result = resolve_effective_foam_entry(
        path,
        "value",
        bashrc=None,
        env={"PATH": str(tmp_path), "WM_PROJECT_DIR": "/runtime/openfoam"},
    )

    assert (result.status, result.value) == ("resolved", "7")
    assert seen["command"] == (str(executable), str(path), "-entry", "value", "-value")
    assert result.runtime == "/runtime/openfoam"


@native
def test_v2412_resolves_local_include_substitution_and_duplicate(tmp_path: Path) -> None:
    included = tmp_path / "inc"
    included.write_text("base 7;\n")
    path = tmp_path / "d"
    path.write_text(
        HEADER + '#include "inc"\n' + "dup 1;\ndup 2;\nref $base;\n"
    )
    ref = resolve_effective_foam_entry(path, "ref")
    duplicate = resolve_effective_foam_entry(path, "dup")
    assert (ref.status, ref.value) == ("resolved", "7")
    assert (duplicate.status, duplicate.value) == ("resolved", "2")
    assert {str(path.resolve()), str(included.resolve())} == set(ref.inspected_files)


def test_executable_directive_requires_explicit_capability_without_running(tmp_path: Path) -> None:
    sentinel = tmp_path / "must-not-exist"
    path = tmp_path / "d"
    path.write_text(
        HEADER + f'pwned #codeStream {{ code #{{ system("touch {sentinel}"); #}}; }};\n'
    )
    result = resolve_effective_foam_entry(path, "pwned")
    assert result.status == "execution_required"
    assert "allow_executable_directives=True" in result.message
    assert not sentinel.exists()


def test_runtime_dependent_include_is_explicitly_unresolved(tmp_path: Path) -> None:
    path = tmp_path / "d"
    path.write_text(HEADER + "#includeFunc residuals\n")
    result = resolve_effective_foam_entry(path, "anything")
    assert result.status == "unresolved"
    assert "runtime-dependent include" in result.message


def test_include_etc_requires_explicit_root_without_running(tmp_path: Path) -> None:
    """Corrected 2026-09-22 (audit finding F2): resolution used to consult
    ``$FOAM_ETC`` alone, so this asserted a single unset variable and a
    message naming it. Resolution now follows the native ``findEtcFile``
    chain -- user, site, then distribution -- so an empty environment reports
    every key that chain depends on, and the message names the searched
    locations (none configured) rather than one variable."""
    path = tmp_path / "d"
    path.write_text(HEADER + '#includeEtc "caseDicts/example"\n')

    result = resolve_effective_foam_entry(path, "anything", bashrc=None, env={})

    assert result.status == "unresolved"
    assert result.environment_keys == (
        "FOAM_API", "FOAM_ETC", "HOME", "WM_PROJECT_DIR",
        "WM_PROJECT_SITE", "WM_PROJECT_VERSION",
    )
    assert "no location configured" in result.message


def test_include_etc_dependency_is_inspected_from_configured_root(
    monkeypatch, tmp_path: Path,
) -> None:
    etc_root = tmp_path / "etc"
    included = etc_root / "caseDicts" / "example"
    included.parent.mkdir(parents=True)
    included.write_text("fromEtc 23;\n")
    path = tmp_path / "d"
    path.write_text(HEADER + '#includeEtc "caseDicts/example"\n')
    executable = tmp_path / "foamDictionary"
    executable.write_text("")
    monkeypatch.setattr(
        "omnidriver.openfoam.effective_dictionary.shutil.which",
        lambda name, path: str(executable),
    )
    monkeypatch.setattr(
        "omnidriver.openfoam.effective_dictionary.subprocess.run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, 0, stdout="23\n", stderr="",
        ),
    )

    result = resolve_effective_foam_entry(
        path,
        "fromEtc",
        bashrc=None,
        env={"PATH": str(tmp_path), "FOAM_ETC": str(etc_root)},
    )

    assert (result.status, result.value) == ("resolved", "23")
    # Corrected 2026-09-22 (audit finding F2): every key the native
    # `findEtcFile` chain depends on is now recorded, not just `FOAM_ETC` --
    # whether HOME/WM_PROJECT_SITE/WM_PROJECT_DIR are set or not changes which
    # file a future run would select.
    assert result.environment_keys == (
        "FOAM_API", "FOAM_ETC", "HOME", "WM_PROJECT_DIR",
        "WM_PROJECT_SITE", "WM_PROJECT_VERSION",
    )
    assert set(result.inspected_files) == {str(path.resolve()), str(included.resolve())}


@native
def test_v2412_resolves_include_etc_and_records_runtime_dependency(
    tmp_path: Path,
) -> None:
    path = tmp_path / "d"
    path.write_text(HEADER + '#includeEtc "caseDicts/profiling/parallel.cfg"\n')

    result = resolve_effective_foam_entry(path, "type")

    dependency = NATIVE_BASHRC.parent / "caseDicts" / "profiling" / "parallel.cfg"
    assert (result.status, result.value) == ("resolved", "parProfiling")
    # Corrected 2026-09-22 (audit finding F2): see the note in
    # test_include_etc_dependency_is_inspected_from_configured_root.
    assert result.environment_keys == (
        "FOAM_API", "FOAM_ETC", "HOME", "WM_PROJECT_DIR",
        "WM_PROJECT_SITE", "WM_PROJECT_VERSION",
    )
    assert str(dependency.resolve()) in result.inspected_files


@native
def test_v2412_ignores_commented_out_directives_and_includes(tmp_path: Path) -> None:
    path = tmp_path / "d"
    path.write_text(
        HEADER
        + '// #includeEtc "caseDicts/setConstraintTypes"\n'
        + '/* #codeStream { code #{ fail; #}; } */\n'
        + 'description "a literal #includeEtc is not a directive";\n'
        + "value 19;\n"
    )
    result = resolve_effective_foam_entry(path, "value")
    assert (result.status, result.value) == ("resolved", "19")
    assert result.inspected_files == (str(path.resolve()),)


def test_environment_include_without_the_required_value_is_unresolved(tmp_path: Path) -> None:
    path = tmp_path / "d"
    path.write_text(HEADER + '#include "$OMNIDRIVER_TEST_INCLUDE"\n')
    result = resolve_effective_foam_entry(path, "anything", env={})
    assert result.status == "unresolved"
    assert result.environment_keys == ("OMNIDRIVER_TEST_INCLUDE",)
    assert "unset environment variable" in result.message


def test_missing_optional_include_is_recorded_as_absence_evidence(
    tmp_path: Path, monkeypatch,
) -> None:
    path = tmp_path / "d"
    missing = tmp_path / "runtime" / "optional.cfg"
    path.write_text(HEADER + f'#includeIfPresent "{missing}"\nvalue 3;\n')

    monkeypatch.setattr(
        "omnidriver.openfoam.effective_dictionary.shutil.which",
        lambda _name, path: None,
    )
    result = resolve_effective_foam_entry(path, "value", bashrc=None, env={})

    assert result.status == "runtime_unavailable"
    assert result.absent_optional_files == (str(missing.resolve()),)


def test_configuration_inspection_identifies_the_selected_evaluator(
    tmp_path: Path, monkeypatch,
) -> None:
    dictionary = tmp_path / "system" / "controlDict"
    dictionary.parent.mkdir()
    dictionary.write_text(HEADER + "value 3;\n")
    evaluator = tmp_path / "foamDictionary"
    evaluator.write_text("")
    monkeypatch.setattr(
        "omnidriver.openfoam.effective_dictionary.shutil.which",
        lambda _name, path: str(evaluator),
    )

    evidence = inspect_effective_foam_configuration(
        tmp_path, ("system/controlDict",), env={"PATH": str(tmp_path)},
    )

    assert evidence[0]["evaluator"] == {
        "name": "foamDictionary", "path": str(evaluator),
    }


@native
def test_v2412_executes_calc_only_with_explicit_opt_in(tmp_path: Path) -> None:
    path = tmp_path / "d"
    path.write_text(HEADER + 'answer #calc "6 * 7";\n')

    gated = resolve_effective_foam_entry(path, "answer")
    resolved = resolve_effective_foam_entry(
        path, "answer", allow_executable_directives=True,
    )

    assert gated.status == "execution_required"
    assert (resolved.status, resolved.value) == ("resolved", "42")


@native
def test_v2412_ignores_a_missing_optional_include(tmp_path: Path) -> None:
    path = tmp_path / "d"
    path.write_text(HEADER + '#includeIfPresent "missing.inc"\nvalue 3;\n')
    result = resolve_effective_foam_entry(path, "value")
    assert (result.status, result.value) == ("resolved", "3")


@native
def test_v2412_resolves_explicit_environment_include_and_records_key(tmp_path: Path) -> None:
    included = tmp_path / "environment.inc"
    included.write_text("fromEnvironment 17;\n")
    path = tmp_path / "d"
    path.write_text(HEADER + '#include "$OMNIDRIVER_TEST_INCLUDE"\n')
    result = resolve_effective_foam_entry(
        path, "fromEnvironment",
        env={**os.environ, "OMNIDRIVER_TEST_INCLUDE": str(included)},
    )
    assert (result.status, result.value) == ("resolved", "17")
    assert result.environment_keys == ("OMNIDRIVER_TEST_INCLUDE",)
    assert str(included.resolve()) in result.inspected_files


def _sourced_native_environment(bashrc: Path, home: Path) -> dict[str, str]:
    """The environment the real bashrc exports for a scratch ``HOME`` --
    ``FOAM_API``, ``WM_PROJECT_VERSION``, ``WM_PROJECT_DIR``,
    ``WM_PROJECT_SITE``, ``FOAM_ETC`` and everything else it sets."""
    script = f'export HOME="{home}"; source "{bashrc}" >/dev/null 2>&1; env'
    completed = subprocess.run(
        ["bash", "-lc", script], capture_output=True, text=True, check=True,
    )
    environment: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            environment[key] = value
    return environment


def _native_foam_etc_file(bashrc: Path, home: Path, name: str) -> str | None:
    """What the real ``foamEtcFile`` binary selects for a scratch ``HOME``,
    or ``None`` if it reports nothing found."""
    script = f'export HOME="{home}"; source "{bashrc}" >/dev/null 2>&1; foamEtcFile "{name}"'
    completed = subprocess.run(["bash", "-lc", script], capture_output=True, text=True)
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


@native
def test_find_etc_file_agrees_with_native_foam_etc_file(tmp_path: Path) -> None:
    """Ground truth for audit finding F2, second pass: this repository's own
    ``find_etc_file`` must select exactly what the real ``foamEtcFile`` binary
    selects, both when nothing shadows the distribution file and when a file
    placed at the top of the search chain does. A scratch ``HOME`` (never the
    real ``~/.OpenFOAM``) is used throughout.

    This is the test the coordinator's re-opened review demanded: the first
    version of ``find_etc_file`` disagreed with native here -- it searched
    ``$HOME/.OpenFOAM/$WM_PROJECT_VERSION`` (``v2412``), a location
    ``foamEtcFile`` never reads on this ESI install, so a file placed there
    was selected by the driver while native kept reading the distribution
    file underneath it.
    """
    from omnidriver.openfoam.effective_dictionary import find_etc_file

    home = tmp_path / "home"
    home.mkdir()
    environment = _sourced_native_environment(NATIVE_BASHRC, home)

    native_selected = _native_foam_etc_file(NATIVE_BASHRC, home, "controlDict")
    ours_selected, _ = find_etc_file("controlDict", environment)
    assert native_selected is not None, "foamEtcFile reported no controlDict at all"
    assert str(ours_selected) == native_selected

    # Now shadow the distribution file at the highest-priority location this
    # environment actually has a version segment for.
    version = environment.get("FOAM_API") or environment.get("WM_PROJECT_VERSION")
    assert version, "native environment must export FOAM_API or WM_PROJECT_VERSION"
    shadow = home / ".OpenFOAM" / version / "controlDict"
    shadow.parent.mkdir(parents=True)
    shadow.write_text("// shadow\n")

    native_selected_with_shadow = _native_foam_etc_file(NATIVE_BASHRC, home, "controlDict")
    ours_selected_with_shadow, _ = find_etc_file("controlDict", environment)
    assert native_selected_with_shadow == str(shadow)
    assert str(ours_selected_with_shadow) == native_selected_with_shadow
