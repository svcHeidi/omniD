"""``rtst_scanner.scan_scheme_registrations`` over files of OpenFOAM v2412's own source, committed verbatim under
``fixtures/openfoam_v2412_src`` (the registration macros, and the headers that name the registered schemes)."""
from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.openfoam.dict_keys_scanner import _strip_comments, source_files
from omnidriver.openfoam.rtst_scanner import scan_rtst_registrations, scan_scheme_registrations

_ROOT = Path(__file__).parent / "fixtures" / "openfoam_v2412_src"


@pytest.fixture(scope="module")
def texts() -> dict[str, str]:
    return {path.relative_to(_ROOT).as_posix(): _strip_comments(path.read_text()) for path in source_files(_ROOT)}


@pytest.fixture(scope="module")
def tables(texts) -> dict[str, dict[str, str]]:
    return scan_scheme_registrations(texts)


def test_a_scheme_registers_under_the_type_name_of_its_class_not_the_class(tables):
    assert tables["ddtSchemes"] == {
        "CrankNicolson": "CrankNicolsonDdtScheme", "Euler": "EulerDdtScheme", "backward": "backwardDdtScheme",
        "steadyState": "steadyStateDdtScheme",
    }
    assert tables["snGradSchemes"]["corrected"] == "correctedSnGrad"
    assert tables["laplacianSchemes"] == {"Gauss": "gaussLaplacianScheme"}


def test_a_type_name_belongs_to_the_class_that_holds_it_not_to_one_nested_before_it(texts):
    # CrankNicolsonDdtScheme.H declares nested classes before its own TypeName.
    assert scan_scheme_registrations(texts)["ddtSchemes"]["CrankNicolson"] == "CrankNicolsonDdtScheme"
    assert "CrankNicolsonDdtScheme" not in scan_scheme_registrations(texts)["ddtSchemes"]


def test_the_gradient_macros_name_their_schemes_three_ways(tables):
    assert tables["gradSchemes"] == {
        "Gauss": "gaussGrad", "leastSquares": "leastSquaresGrad",
        "cellLimited": "cellLimitedGrad", "cellLimited<Venkatakrishnan>": "cellLimited", "cellLimited<cubic>": "cellLimited",
    }


def test_a_convection_scheme_and_a_div_scheme_fill_the_one_div_table(tables):
    assert set(tables["divSchemes"]) == {"Gauss", "bounded"}
    assert tables["divSchemes"]["bounded"] == "boundedConvectionScheme"


def test_a_limited_interpolation_scheme_is_named_by_the_macro_argument_whatever_line_it_is_written_on(tables):
    interpolation = tables["interpolationSchemes"]
    assert {"linear", "upwind", "MUSCL", "limitedMUSCL", "vanLeer", "limitedVanLeer", "Phi"} <= set(interpolation)
    assert interpolation["linear"] == "linear"


def test_the_fit_macros_written_across_lines_register_their_first_argument(tables):
    assert tables["snGradSchemes"]["linearFit"] == "linearFit"


def test_a_scheme_added_to_its_table_without_a_macro_registers_too(tables):
    assert tables["interpolationSchemes"]["harmonic"] == "harmonic"


def test_a_macro_inside_a_define_registers_nothing(texts):
    # cellLimitedGrads.C calls makeFvLimitedGradTypeScheme(SS, scalar, Limiter) inside its own #define.
    assert not any("SS" in name or "Limiter" == name for names in scan_scheme_registrations(texts).values() for name in names)


def test_the_ode_solvers_are_found_by_the_runtime_selection_scan(texts):
    assert scan_rtst_registrations(texts)["ODESolver"] == {"Euler": "Euler", "RKF45": "RKF45"}
