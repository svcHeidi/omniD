"""What a case loads at run time resolves from an injected environment, so no OpenFOAM needs sourcing."""

from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.openfoam.build_products import _control_dict_libs as _parse_control_dict_libs
from omnidriver.openfoam.build_products import case_runtime_dependencies


def resolve_runtime_dependencies(case_root: Path, *, env):
    return case_runtime_dependencies(case_root, env=env)


def _write_control_dict(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "controlDict"
    p.write_text(
        "FoamFile\n{\n    version 2.0;\n    format ascii;\n"
        "    class dictionary;\n    object controlDict;\n}\n\n" + body
    )
    return p


class TestParseControlDictLibs:
    """Edge cases of _parse_control_dict_libs."""

    def test_returns_empty_tuple_when_libs_is_absent(self, tmp_path: Path) -> None:
        p = _write_control_dict(tmp_path, "application simpleFoam;\n")
        assert _parse_control_dict_libs(p) == ()

    def test_returns_empty_tuple_when_libs_is_an_empty_list(self, tmp_path: Path) -> None:
        p = _write_control_dict(tmp_path, "libs\n(\n);\n")
        assert _parse_control_dict_libs(p) == ()

    def test_strips_quotes_from_a_single_entry(self, tmp_path: Path) -> None:
        p = _write_control_dict(tmp_path, 'libs\n(\n    "libverificationModels.so"\n);\n')
        assert _parse_control_dict_libs(p) == ("libverificationModels.so",)

    def test_parses_multiple_entries_in_declaration_order(self, tmp_path: Path) -> None:
        p = _write_control_dict(
            tmp_path,
            'libs\n(\n    "libfoo.so"\n    "libbar.so"\n);\n',
        )
        assert _parse_control_dict_libs(p) == ("libfoo.so", "libbar.so")

    def test_returns_empty_tuple_when_file_does_not_exist(self, tmp_path: Path) -> None:
        assert _parse_control_dict_libs(tmp_path / "missing" / "controlDict") == ()


def _make_lib(directory: Path, name: str, extension: str, content: bytes = b"x") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    lib = directory / f"lib{name}{extension}"
    lib.write_bytes(content)
    return lib


def _loading(case_root: Path, entry: str) -> Path:
    (case_root / "system").mkdir(parents=True, exist_ok=True)
    (case_root / "system" / "controlDict").write_text(f'libs\n(\n    "{entry}"\n);\n')
    return case_root


def test_finds_a_library_in_whichever_defined_directory_holds_it(tmp_path: Path) -> None:
    """A library whose Make/files names FOAM_MODULE_LIBBIN can install to FOAM_USER_LIBBIN."""
    user_libbin = tmp_path / "user_libbin"
    _make_lib(user_libbin, "physicsModel", ".dylib")
    env = {"FOAM_USER_LIBBIN": str(user_libbin), "PATH": ""}

    deps = {d.name: d for d in resolve_runtime_dependencies(_loading(tmp_path / "case", "libphysicsModel.so"), env=env)}
    assert deps["physicsModel"].path == user_libbin / "libphysicsModel.dylib"


def test_tries_both_platform_extensions(tmp_path: Path) -> None:
    lib_dir = tmp_path / "libbin"
    _make_lib(lib_dir, "fieldFunctionObjects", ".so")
    env = {"FOAM_LIBBIN": str(lib_dir), "PATH": ""}
    deps = {d.name: d for d in resolve_runtime_dependencies(_loading(tmp_path / "case", "libfieldFunctionObjects.so"), env=env)}
    assert deps["fieldFunctionObjects"].path == lib_dir / "libfieldFunctionObjects.so"


def test_a_loaded_library_absent_everywhere_is_reported_not_omitted(tmp_path: Path) -> None:
    deps = {d.name: d for d in resolve_runtime_dependencies(_loading(tmp_path / "case", "libmissing.so"), env={"PATH": ""})}
    assert deps["missing"].path is None
    assert deps["missing"].required is True


def test_a_bare_library_named_in_controldict_libs_becomes_required(tmp_path: Path) -> None:
    """A library no solver links, loaded by the case's controlDict libs, as cardiacFOAM's manufactured tutorials load libverificationModels."""
    case_root = tmp_path / "case"
    lib_dir = tmp_path / "user_libbin"
    _make_lib(lib_dir, "verificationModels", ".dylib")
    (case_root / "system").mkdir(parents=True)
    (case_root / "system" / "controlDict").write_text(
        'application simpleFoam;\n\nlibs\n(\n    "libverificationModels.so"\n);\n'
    )
    env = {"FOAM_USER_LIBBIN": str(lib_dir), "PATH": ""}
    deps = {d.name: d for d in resolve_runtime_dependencies(case_root, env=env)}
    assert deps["verificationModels"].required is True
    assert deps["verificationModels"].path == lib_dir / "libverificationModels.dylib"


def test_a_case_local_library_path_expands_foam_case_and_wm_options(tmp_path: Path) -> None:
    """A case-local library, as cardiacFOAM's monodomainTotalLagrangianEM loads; $WM_OPTIONS comes from the executor's environment."""
    case_root = tmp_path / "case"
    built_lib_dir = case_root / "platforms" / "myOptions" / "lib"
    built_lib_dir.mkdir(parents=True)
    built_lib = built_lib_dir / "libmanufacturedMonodomainTotalLagrangianEM.so"
    built_lib.write_bytes(b"compiled")
    (case_root / "system").mkdir(parents=True, exist_ok=True)
    (case_root / "system" / "controlDict").write_text(
        "libs\n(\n"
        '    "$FOAM_CASE/platforms/$WM_OPTIONS/lib/libmanufacturedMonodomainTotalLagrangianEM.so"\n'
        ");\n"
    )
    env = {"WM_OPTIONS": "myOptions", "PATH": ""}
    deps = {d.name: d for d in resolve_runtime_dependencies(case_root, env=env)}
    assert deps["manufacturedMonodomainTotalLagrangianEM"].path == built_lib
    assert deps["manufacturedMonodomainTotalLagrangianEM"].required is True


def test_a_case_local_library_path_with_unset_wm_options_is_unavailable_not_guessed(
    tmp_path: Path,
) -> None:
    case_root = tmp_path / "case"
    (case_root / "system").mkdir(parents=True, exist_ok=True)
    (case_root / "system" / "controlDict").write_text(
        "libs\n(\n"
        '    "$FOAM_CASE/platforms/$WM_OPTIONS/lib/libmanufacturedMonodomainTotalLagrangianEM.so"\n'
        ");\n"
    )
    env = {"PATH": ""}
    deps = {d.name: d for d in resolve_runtime_dependencies(case_root, env=env)}
    assert deps["manufacturedMonodomainTotalLagrangianEM"].path is None
    assert deps["manufacturedMonodomainTotalLagrangianEM"].required is True


def test_a_case_with_no_controldict_loads_nothing(tmp_path: Path) -> None:
    assert resolve_runtime_dependencies(tmp_path / "case_without_controldict", env={"PATH": ""}) == ()


def test_a_case_with_a_gmsh_geometry_declares_gmsh(tmp_path, monkeypatch):
    """A case carrying a .geo cannot mesh without the gmsh binary, so it declares that need."""
    case = tmp_path / "case"
    (case / "system").mkdir(parents=True)
    (case / "box.geo").write_text("SetFactory(\"OpenCASCADE\");\n")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "gmsh").write_text("#!/bin/sh\n")
    (fake_bin / "gmsh").chmod(0o755)

    deps = {
        d.name: d
        for d in resolve_runtime_dependencies(case, env={"PATH": str(fake_bin)})
    }
    assert "gmsh" in deps
    assert deps["gmsh"].required is True
    assert deps["gmsh"].path == fake_bin / "gmsh"


def test_a_case_without_a_geometry_does_not_declare_gmsh(tmp_path):
    """Declaring gmsh for every case would make the test above pass regardless of the .geo."""
    case = tmp_path / "case"
    (case / "system").mkdir(parents=True)

    deps = {d.name: d for d in resolve_runtime_dependencies(case, env={"PATH": ""})}
    assert "gmsh" not in deps


def test_a_missing_gmsh_is_reported_unavailable_not_omitted(tmp_path):
    case = tmp_path / "case"
    (case / "system").mkdir(parents=True)
    (case / "mesh" ).mkdir()
    (case / "mesh" / "box.geo").write_text("")

    deps = {d.name: d for d in resolve_runtime_dependencies(case, env={"PATH": ""})}
    assert deps["gmsh"].required is True
    assert deps["gmsh"].path is None
