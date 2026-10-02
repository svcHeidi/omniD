"""Contract tests for the read-only inspection of a dictionary's include closure."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from omnidriver.openfoam.effective_dictionary import inspect_effective_foam_configuration
from omnidriver.openfoam.openfoam_environment import discover_openfoam_bashrc


HEADER = "FoamFile { version 2.0; format ascii; class dictionary; object d; }\n"
ETC_KEYS = (
    "FOAM_API", "FOAM_CONFIG_ETC", "FOAM_CONFIG_MODE", "FOAM_ETC", "HOME",
    "WM_PROJECT_DIR", "WM_PROJECT_INST_DIR", "WM_PROJECT_SITE", "WM_PROJECT_VERSION",
)
NATIVE_BASHRC = discover_openfoam_bashrc()
native = pytest.mark.skipif(
    NATIVE_BASHRC is None,
    reason="no OpenFOAM installation discoverable; native effective resolution is not verified",
)


def _inspect(path: Path, env: dict[str, str]) -> dict:
    (evidence,) = inspect_effective_foam_configuration(path.parent, (path.name,), env=env)
    return evidence


def test_a_local_include_is_followed(tmp_path: Path) -> None:
    included = tmp_path / "inc"
    included.write_text("base 7;\n")
    path = tmp_path / "d"
    path.write_text(HEADER + '#include "inc"\nref $base;\n')
    evidence = _inspect(path, {})
    assert evidence["status"] == "inspected"
    assert set(evidence["inspected_files"]) == {str(path.resolve()), str(included.resolve())}


def test_an_executable_directive_is_unresolved_and_never_run(tmp_path: Path) -> None:
    sentinel = tmp_path / "must-not-exist"
    path = tmp_path / "d"
    path.write_text(
        HEADER + f'pwned #codeStream {{ code #{{ system("touch {sentinel}"); #}}; }};\n'
    )
    evidence = _inspect(path, {})
    assert evidence["status"] == "unresolved"
    assert "executable dictionary directive" in evidence["message"]
    assert not sentinel.exists()


def test_runtime_dependent_include_is_explicitly_unresolved(tmp_path: Path) -> None:
    path = tmp_path / "d"
    path.write_text(HEADER + "#includeFunc residuals\n")
    evidence = _inspect(path, {})
    assert evidence["status"] == "unresolved"
    assert "runtime-dependent include" in evidence["message"]


def test_include_etc_without_a_configured_root_is_unresolved_and_reports_every_key(tmp_path: Path) -> None:
    """Every key find_etc_file's search chain depends on is reported, not just FOAM_ETC."""
    path = tmp_path / "d"
    path.write_text(HEADER + '#includeEtc "caseDicts/example"\n')

    evidence = _inspect(path, {})

    assert evidence["status"] == "unresolved"
    assert evidence["environment_keys"] == list(ETC_KEYS)
    assert "no location configured" in evidence["message"]


def test_include_etc_dependency_is_inspected_from_configured_root(tmp_path: Path) -> None:
    etc_root = tmp_path / "etc"
    included = etc_root / "caseDicts" / "example"
    included.parent.mkdir(parents=True)
    included.write_text("fromEtc 23;\n")
    path = tmp_path / "d"
    path.write_text(HEADER + '#includeEtc "caseDicts/example"\n')

    evidence = _inspect(path, {"FOAM_ETC": str(etc_root)})

    assert evidence["status"] == "inspected"
    assert evidence["environment_keys"] == list(ETC_KEYS)
    assert set(evidence["inspected_files"]) == {str(path.resolve()), str(included.resolve())}


def test_commented_out_directives_and_includes_are_not_directives(tmp_path: Path) -> None:
    path = tmp_path / "d"
    path.write_text(
        HEADER
        + '// #includeEtc "caseDicts/setConstraintTypes"\n'
        + '/* #codeStream { code #{ fail; #}; } */\n'
        + 'description "a literal #includeEtc is not a directive";\n'
        + "value 19;\n"
    )
    evidence = _inspect(path, {})
    assert evidence["status"] == "inspected"
    assert evidence["inspected_files"] == [str(path.resolve())]


def test_environment_include_without_the_required_value_is_unresolved(tmp_path: Path) -> None:
    path = tmp_path / "d"
    path.write_text(HEADER + '#include "$OMNIDRIVER_TEST_INCLUDE"\n')
    evidence = _inspect(path, {})
    assert evidence["status"] == "unresolved"
    assert evidence["environment_keys"] == ["OMNIDRIVER_TEST_INCLUDE"]
    assert "unset environment variable" in evidence["message"]


def test_environment_include_is_followed_and_its_key_recorded(tmp_path: Path) -> None:
    included = tmp_path / "environment.inc"
    included.write_text("fromEnvironment 17;\n")
    path = tmp_path / "d"
    path.write_text(HEADER + '#include "$OMNIDRIVER_TEST_INCLUDE"\n')
    evidence = _inspect(path, {"OMNIDRIVER_TEST_INCLUDE": str(included)})
    assert evidence["status"] == "inspected"
    assert evidence["environment_keys"] == ["OMNIDRIVER_TEST_INCLUDE"]
    assert str(included.resolve()) in evidence["inspected_files"]


def test_missing_optional_include_is_recorded_as_absence_evidence(tmp_path: Path) -> None:
    path = tmp_path / "d"
    missing = tmp_path / "runtime" / "optional.cfg"
    path.write_text(HEADER + f'#includeIfPresent "{missing}"\nvalue 3;\n')
    evidence = _inspect(path, {})
    assert evidence["status"] == "inspected"
    assert evidence["absent_optional_files"] == [str(missing.resolve())]


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


def _sourced_native_environment(bashrc: Path, home: Path) -> dict[str, str]:
    """The environment the real bashrc exports for a scratch ``HOME``."""
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


def _native_foam_etc_file(
    bashrc: Path, home: Path, name: str, *, extra_env: dict[str, str] | None = None,
) -> str | None:
    """What the real ``foamEtcFile`` binary selects for a scratch ``HOME``,
    or ``None`` if it reports nothing found."""
    exports = "".join(f'export {key}="{value}"; ' for key, value in (extra_env or {}).items())
    script = (
        f'export HOME="{home}"; source "{bashrc}" >/dev/null 2>&1; {exports}'
        f'foamEtcFile "{name}"'
    )
    completed = subprocess.run(["bash", "-lc", script], capture_output=True, text=True)
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def _native_foam_etc_file_list(
    bashrc: Path, home: Path, name: str, *, extra_env: dict[str, str] | None = None,
) -> tuple[str, ...]:
    """The full ``foamEtcFile -list`` candidate order for a scratch ``HOME``."""
    exports = "".join(f'export {key}="{value}"; ' for key, value in (extra_env or {}).items())
    script = (
        f'export HOME="{home}"; source "{bashrc}" >/dev/null 2>&1; {exports}'
        f'foamEtcFile -list "{name}"'
    )
    completed = subprocess.run(
        ["bash", "-lc", script], capture_output=True, text=True, check=True,
    )
    return tuple(line for line in completed.stdout.splitlines() if line.strip())


@native
def test_find_etc_file_agrees_with_native_foam_etc_file(tmp_path: Path) -> None:
    """Uses a scratch ``HOME``, never the real ``~/.OpenFOAM``."""
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


@native
def test_find_etc_file_matches_native_list_entry_for_entry(tmp_path: Path) -> None:
    """Candidate order must match, entry for entry, not merely agree on the final selection."""
    from omnidriver.openfoam.effective_dictionary import find_etc_file

    home = tmp_path / "home"
    home.mkdir()
    base_environment = _sourced_native_environment(NATIVE_BASHRC, home)

    config_etc_dir = tmp_path / "config_etc_override"
    config_etc_dir.mkdir()

    cases: dict[str, dict[str, str]] = {
        "default mode": {},
        "FOAM_CONFIG_ETC set": {"FOAM_CONFIG_ETC": str(config_etc_dir)},
        "FOAM_CONFIG_MODE=o": {"FOAM_CONFIG_MODE": "o"},
        "FOAM_CONFIG_MODE=u": {"FOAM_CONFIG_MODE": "u"},
        "FOAM_CONFIG_MODE=go": {"FOAM_CONFIG_MODE": "go"},
    }

    report_lines = []
    for label, extra_env in cases.items():
        native_list = _native_foam_etc_file_list(
            NATIVE_BASHRC, home, "controlDict", extra_env=extra_env,
        )
        ours_selected, ours_candidates = find_etc_file(
            "controlDict", {**base_environment, **extra_env},
        )
        ours_list = tuple(str(candidate) for candidate in ours_candidates)
        report_lines.append(f"{label}:\n  native: {native_list}\n  ours:   {ours_list}")
        assert ours_list == native_list, "\n".join(report_lines)

        native_selected = _native_foam_etc_file(
            NATIVE_BASHRC, home, "controlDict", extra_env=extra_env,
        )
        assert (str(ours_selected) if ours_selected else None) == native_selected, (
            "\n".join(report_lines)
        )

    print("\n\n".join(report_lines))
