"""Gate 2: the problem's data equals what cardiacFOAM's code states, read from verbatim snippets of that code.

A change to the owner's C++ or case files that the data does not follow fails here, once the snippets are
refreshed from the new commit.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

sympy = pytest.importorskip("sympy")

from omnidriver.verifier.problem import load_problem

FIXTURES = Path(__file__).parent / "fixtures" / "cardiacfoam"
IONIC = "src/ionicModels/verificationModels/monodomainFDAManufactured/monodomainFDAManufactured_2014.H"
REFERENCE = "src/verificationModels/monodomainVerification/manufacturedFDAReference.H"
ELECTRO = "tutorials/manufacturedSolutions/monodomainPseudoECG/constant/electroProperties"
CONTROL = "tutorials/manufacturedSolutions/monodomainPseudoECG/system/controlDict"
SWEEP = "tutorials/manufacturedSolutions/monodomainPseudoECG/setup/studies/cartesianConvergence/sweep_hex_convergence.json"
# The C++ names its constants and state indices; the data names them so.
CXX_NAMES = {"Chi": "chi", "Fx": "F", "Gx": "G"}


def _snippets() -> dict[str, str]:
    return {name: (FIXTURES / name).read_text() for name in (IONIC, REFERENCE, ELECTRO, CONTROL, SWEEP)}


def _body(text: str, commit: str) -> list[str]:
    header, *lines = text.splitlines()
    assert commit in header, header
    return [line for line in lines if line.strip() not in ("// ...", "# ...")]


def _statements(lines: list[str]) -> list[tuple[str, str]]:
    """``lhs = rhs;`` statements in source order, with C++ spelling rewritten to the data's expression syntax."""
    found = []
    for statement in " ".join(lines).split(";"):
        if "=" not in statement:
            continue
        lhs, rhs = (part.strip() for part in statement.split("=", 1))
        lhs = lhs.removeprefix("const scalar ").strip()
        rhs = rhs.replace("Foam::", "").replace("constant::mathematical::pi", "pi")
        rhs = re.sub(r"\b(?:STATES|CONSTANTS)\[(\w+)\]|\b(\w+)\[i\]", lambda m: m.group(1) or m.group(2), rhs)
        rhs = re.sub(r"\b\w+\b", lambda m: CXX_NAMES.get(m.group(0), m.group(0)), rhs)
        found.append((lhs, rhs))
    return found


def _sym(text: str, names: dict) -> object:
    from sympy.parsing.sympy_parser import rationalize, standard_transformations

    # Rationals: the C++ writes 1.0 and 0.5 where the data writes 1 and 1/2.
    return sympy.parse_expr(
        text, local_dict={"pow": lambda a, b: a**b, "pi": sympy.pi, **names},
        transformations=(*standard_transformations, rationalize),
    )


def _same(left: str, right: str, names: dict | None = None) -> bool:
    return sympy.simplify(_sym(left, names or {}) - _sym(right, names or {})) == 0


def drift(snippets: dict[str, str], problem: dict) -> list[str]:
    commit = problem["native"]["cardiacfoam"]["commit"]
    found = []

    constants = dict(_statements(_body(snippets[IONIC], commit)))
    betas = [rhs for lhs, rhs in _statements(_body(snippets[IONIC], commit)) if lhs == "CONSTANTS[Beta]"]
    if float(constants["CONSTANTS[Cm]"]) != problem["parameters"]["Cm"]:
        found.append("ionic Cm")
    if float(constants["CONSTANTS[Chi]"]) != problem["parameters"]["chi"]:
        found.append("ionic Chi")
    native_beta = problem["derived"]["Beta"]["native"]
    if [float(value) for value in betas] != [native_beta[str(d)] for d in problem["dimensions"]]:
        found.append("ionic Beta")
    rates = problem["cell_model"]["rates"]
    for state in problem["cell_model"]["states"]:
        if not _same(constants[f"RATES[{state}]"], rates[state]):
            found.append(f"rate {state}")
    if not _same(constants["ALGEBRAIC[Iion]"], problem["cell_model"]["Iion"]):
        found.append("Iion")

    reference = _statements(_body(snippets[REFERENCE], commit))
    for name in ("F", "G"):
        by_dimension = [rhs for lhs, rhs in reference if lhs == f"{name}[i]"]
        for d, rhs in zip(problem["dimensions"], by_dimension, strict=True):
            if not _same(rhs, problem["fields"][name][str(d)]):
                found.append(f"field {name} {d}D")
    local = {}
    exact = {}
    for lhs, rhs in reference:
        if lhs.endswith("[i]"):
            exact.setdefault(lhs.removesuffix("[i]"), rhs)
        else:
            local[lhs] = _sym(rhs, local)
    for name in ("V", "u1", "u2", "u3"):
        if not _same(exact[name], problem["exact"][name], local):
            found.append(f"exact {name}")

    electro = {line.split()[0]: float(line.split()[-1].rstrip(";")) for line in _body(snippets[ELECTRO], commit)}
    if (electro["chi"], electro["cm"]) != (problem["parameters"]["chi"], problem["parameters"]["Cm"]):
        found.append("electroProperties chi/cm")
    (end_time,) = _body(snippets[CONTROL], commit)
    if float(end_time.split()[-1].rstrip(";")) != problem["time"]["end"]:
        found.append("endTime")

    conductivity, *ladder = _body(snippets[SWEEP], commit)
    xx, _, _, yy, _, zz = (float(v) for v in conductivity.split("(")[1].split(")")[0].split())
    parameters = problem["parameters"]
    if (xx, yy, zz) != (parameters["sigma_xx"], parameters["sigma_yy"], parameters["sigma_zz"]):
        found.append("conductivity")
    values = [float(line) for line in ladder]
    hex_ladder = problem["refinement"]["hex"]
    if values != [*hex_ladder["cells_per_axis"], *hex_ladder["dt"]]:
        found.append("hex refinement")
    return found


def test_the_problem_data_matches_cardiacfoam():
    assert drift(_snippets(), load_problem("fda_monodomain")) == []


@pytest.mark.parametrize(
    ("snippet", "old", "new", "reported"),
    [
        (IONIC, "CONSTANTS[Cm]  = 2.0", "CONSTANTS[Cm]  = 2.5", "ionic Cm"),
        (IONIC, "CONSTANTS[Beta] = -8.6", "CONSTANTS[Beta] = -8.7", "ionic Beta"),
        (IONIC, "pow(STATES[u2], 3)", "pow(STATES[u2], 2)", "rate u2"),
        (IONIC, "/ CONSTANTS[Chi]", "* CONSTANTS[Chi]", "Iion"),
        (REFERENCE, "cos(3.0*", "cos(4.0*", "field F 3D"),
        (REFERENCE, "Foam::pow(Gx[i], -0.5)", "Foam::pow(Gx[i], 0.5)", "exact u2"),
        (ELECTRO, "] 3;", "] 4;", "electroProperties chi/cm"),
        (CONTROL, "0.2;", "0.3;", "endTime"),
        (SWEEP, "0.121585420", "0.121585", "conductivity"),
        (SWEEP, "0.000140174", "0.000140", "hex refinement"),
    ],
)
def test_a_changed_snippet_is_reported(snippet, old, new, reported):
    snippets = _snippets()
    assert old in snippets[snippet]
    snippets[snippet] = snippets[snippet].replace(old, new, 1)
    assert drift(snippets, load_problem("fda_monodomain")) == [reported]
