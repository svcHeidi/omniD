"""Contract tests for explicit native effective dictionary resolution."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from omnidriver.openfoam.effective_dictionary import resolve_effective_foam_entry


HEADER = "FoamFile { version 2.0; format ascii; class dictionary; object d; }\n"
V2412_BASHRC = Path("/Volumes/OpenFOAM-v2412/etc/bashrc")
native = pytest.mark.skipif(
    not V2412_BASHRC.exists(),
    reason="OpenFOAM v2412 runtime unavailable; native effective resolution is not verified",
)


def test_missing_runtime_is_explicit_not_a_lexical_fallback(tmp_path: Path) -> None:
    path = tmp_path / "d"
    path.write_text(HEADER + "value 1;\n")
    result = resolve_effective_foam_entry(path, "value", bashrc=tmp_path / "missing-bashrc")
    assert result.status == "runtime_unavailable"
    assert result.value is None
    assert result.parser == "foamDictionary"


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
    path.write_text(HEADER + "#includeEtc \"caseDicts/setConstraintTypes\"\n")
    result = resolve_effective_foam_entry(path, "anything")
    assert result.status == "unresolved"
    assert "runtime-dependent include" in result.message


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
