"""Gate 2 for the anisotropic problem: its data equals what cardiacFOAM's code states, read from verbatim snippets.

What it shares with the FDA problem (the cell model, the solver's equation, the units, the wall, the norm) is read
from the FDA fixtures through the FDA gate's own checks; the spatial factor, the source, the conductivity, the
verifier's configuration and the ladders are read from the snippets in ``fixtures/cardiacfoam_anisotropic``.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

sympy = pytest.importorskip("sympy")

import test_native_drift as fda
from omnidriver.verifier.problem import load_problem

FIXTURES = Path(__file__).parent / "fixtures" / "cardiacfoam_anisotropic"
# The snippets here and the FDA gate's of the same native file hold different lines, so they are keyed apart.
OWN_KEY = "anisotropic:"
REFERENCE = OWN_KEY + "src/verificationModels/monodomainVerification/manufacturedAnisotropicMonodomainReference.H"
VERIFIER = OWN_KEY + "src/verificationModels/monodomainVerification/manufacturedAnisotropicMonodomainVerifier.C"
ELECTRO = OWN_KEY + f"{fda.CASE}/constant/electroProperties"
SWEEP = OWN_KEY + f"{fda.CASE}/setup/studies/cartesianConvergence/sweep_hex_convergence.json"
TET_SWEEP = OWN_KEY + f"{fda.CASE}/setup/studies/tetConvergence/sweep_tet_generic.json"
OWN = (REFERENCE, VERIFIER, ELECTRO, SWEEP, TET_SWEEP)
# OpenFOAM's symmTensor components in storage order, and the conductivity entries the data names them by.
SYMM_TENSOR = ("xx", "xy", "xz", "yy", "yz", "zz")
# The tensor is symmetric, so the C++'s transposed component is the same parameter.
CXX_TENSOR_ENTRIES = {"xx": "xx", "yy": "yy", "zz": "zz", "xy": "xy", "yx": "xy", "xz": "xz", "zx": "xz",
                      "yz": "yz", "zy": "yz"}


def _snippets() -> dict[str, str]:
    return {**fda._snippets(), **{name: (FIXTURES / name.removeprefix(OWN_KEY)).read_text() for name in OWN}}


def _native_statements(lines: list[str]) -> list[tuple[str, str]]:
    """The reference's statements in source order, spelled in the data's syntax: the coordinates and conductivity
    entries by name, the field index ``[cellI]`` as ``[i]``."""
    text = " ".join(lines).replace("[cellI]", "[i]")
    text = re.sub(r"\bc\.([xyz])\(\)", r"\1", text)
    text = re.sub(r"\bK\.(\w\w)\(\)", lambda m: f"sigma_{CXX_TENSOR_ENTRIES[m.group(1)]}", text)
    text = re.sub(r"\bbeta\b", "Beta", text)
    return fda._statements([text])


def _reference_drift(snippets: dict[str, str], problem: dict, commit: str) -> list[str]:
    """The spatial factors against ``fields``, and V, the states and the source against the data's expressions with
    the factors left as symbols, so one wrong factor is reported once."""
    values = {name: fda._sym(str(value), {}) for name, value in problem["parameters"].items()}
    symbols = {name: sympy.Symbol(name) for name in ("F", "G")}
    names = {"pow": lambda a, b: a**b, "sqr": lambda a: a**2, "pi": sympy.pi, **values, **symbols}
    local: dict[str, object] = {}
    factors: dict[str, object] = {}
    exact: dict[str, object] = {}
    for lhs, rhs in _native_statements(fda._body(snippets[REFERENCE], commit)):
        parsed = fda._sym(rhs, {**names, **local})
        if lhs == "F[i]":
            factors["F"] = parsed
        elif lhs == "G":
            factors["G"] = parsed
        elif lhs.endswith("[i]"):
            exact[lhs.removesuffix("[i]")] = parsed
        else:
            local[lhs] = parsed
    found = []
    fields = {name: fda._sym(by_dimension["3"], values) for name, by_dimension in problem["fields"].items()}
    for name, native in factors.items():
        if sympy.simplify(native - fields[name]) != 0:
            found.append(f"field {name}")
    for name in ("V", "u1", "u2", "u3"):
        if sympy.simplify(exact[name] - fda._sym(problem["exact"][name], {**values, **symbols})) != 0:
            found.append(f"exact {name}")
    declared = fda._sym(problem["source"]["expression"], {**values, **fields})
    if sympy.simplify(exact["source"] - declared) != 0:
        found.append("source")
    return found


def drift(snippets: dict[str, str], problem: dict) -> list[str]:
    commit = problem["native"]["cardiacfoam"]["commit"]
    found = []

    constants = dict(fda._statements(fda._body(snippets[fda.IONIC], commit)))
    betas = [rhs for lhs, rhs in fda._statements(fda._body(snippets[fda.IONIC], commit)) if lhs == "CONSTANTS[Beta]"]
    if float(constants["CONSTANTS[Cm]"]) != problem["parameters"]["Cm"]:
        found.append("ionic Cm")
    if float(constants["CONSTANTS[Chi]"]) != problem["parameters"]["chi"]:
        found.append("ionic Chi")
    # The verifier reads Beta from the 3D ionic model, the last of the three the model sets.
    if float(betas[-1]) != problem["parameters"]["Beta"]:
        found.append("ionic Beta")
    unknown = problem["pde"]["unknown"]
    if float(constants[f"RATES[{unknown}]"]) != 0 or problem["cell_model"]["inputs"] != [unknown]:
        found.append("cell model integrates V")
    for state, rate in problem["cell_model"]["rates"].items():
        if not fda._same(constants[f"RATES[{state}]"], rate):
            found.append(f"rate {state}")
    if not fda._same(constants["ALGEBRAIC[Iion]"], problem["cell_model"]["Iion"]):
        found.append("Iion")
    found += fda._pde_drift(snippets, problem, commit)
    found += fda._units_drift(snippets, problem, commit)
    found += fda._boundary_drift(snippets, problem, commit)
    found += fda._domain_drift(snippets, problem, commit)
    found += fda._time_drift(snippets, problem, commit)
    found += fda._norms_drift({**snippets, fda.VERIFIER: snippets[VERIFIER]}, problem, commit)
    found += _reference_drift(snippets, problem, commit)
    found += _configuration_drift(snippets, problem, commit)
    found += _ladder_drift(snippets, problem, commit)
    return found


def _configuration_drift(snippets: dict[str, str], problem: dict, commit: str) -> list[str]:
    found = []
    native = problem["native"]["cardiacfoam"]
    electro = {line.split()[0]: line.split()[-1].rstrip(";") for line in fda._body(snippets[ELECTRO], commit)}
    conductivity = next(line for line in fda._body(snippets[ELECTRO], commit) if line.split()[0] == "conductivity")
    entries = [float(v) for v in conductivity.split("(")[1].split(")")[0].split()]
    if entries != [problem["parameters"][f"sigma_{entry}"] for entry in SYMM_TENSOR]:
        found.append("conductivity")
    if (float(electro["chi"]), float(electro["cm"])) != (problem["parameters"]["chi"], problem["parameters"]["Cm"]):
        found.append("electroProperties chi/cm")
    if electro["type"] != native["verification_model"]:
        found.append("verifier type")
    if electro["dimension"].strip('"') != f"{problem['dimensions'][0]}D" or len(problem["dimensions"]) != 1:
        found.append("dimension")

    verifier = " ".join(" ".join(fda._body(snippets[VERIFIER], commit)).split())
    family = f'model.verificationFamily() != "{native["ionic_model"]}"'
    if family not in verifier or f"model.geometricDimension() != {problem['dimensions'][0]}" not in verifier:
        found.append("verifier configuration")
    box = problem["domain"]["box"]
    if (box != [[0, 1]] * 3 or "unitMin(vector::zero)" not in verifier or "unitMax(vector::one)" not in verifier
            or "mag(bounds.min() - unitMin) > cubeTolerance" not in verifier
            or "mag(bounds.max() - unitMax) > cubeTolerance" not in verifier):
        found.append("verifier domain")
    return found


def _ladder_drift(snippets: dict[str, str], problem: dict, commit: str) -> list[str]:
    """The hex sweep's last four rows and the tet sweep's two anisotropic groups: tensor, verifier, cells and dt."""
    found = []
    parameters = problem["parameters"]
    wanted = [parameters[f"sigma_{entry}"] for entry in SYMM_TENSOR]

    def tensor(line: str) -> list[float]:
        return [float(v) for v in line.split("(")[1].split(")")[0].split()]

    hex_body = [line.strip() for line in fda._body(snippets[SWEEP], commit)]
    conductivity, *verifiers_and_levels = hex_body
    verifiers = [line.strip('",') for line in verifiers_and_levels[:4]]
    levels = [float(line) for line in verifiers_and_levels[4:]]
    hex_ladder = problem["refinement"]["hex"]
    if tensor(conductivity) != wanted:
        found.append("hex conductivity")
    if set(verifiers) != {problem["native"]["cardiacfoam"]["verification_model"]}:
        found.append("hex verifier")
    if levels != [*hex_ladder["cells_per_axis"], *hex_ladder["dt"]]:
        found.append("hex refinement")

    tet = problem["refinement"]["tet"]
    first, last, verifier_first, verifier_last, *ladder = [line.strip() for line in fda._body(snippets[TET_SWEEP], commit)]
    if tensor(first.strip('",')) != wanted or tensor(last.strip('",')) != wanted:
        found.append("tet conductivity")
    if {verifier_first.strip('",'), verifier_last.strip('",')} != {problem["native"]["cardiacfoam"]["verification_model"]}:
        found.append("tet verifier")
    values = [float(line) for line in ladder]
    cells, dts = values[:8], values[8:]
    if cells != 2 * tet["cells_per_axis"] or dts != 2 * tet["dt"]:
        found.append("tet refinement")
    geo = " ".join(fda._body(snippets[fda.TET_GEO], commit))
    edge = problem["domain"]["box"][0][1] - problem["domain"]["box"][0][0]
    if (edge != 1 or "(lc = 1/N)" not in geo
            or not all(f"Mesh.MeshSize{bound} = lc;" in geo for bound in ("Min", "Max"))):
        found.append("tet mesh size")
    return found


def test_the_problem_data_matches_cardiacfoam():
    assert drift(_snippets(), load_problem("anisotropic_monodomain")) == []


@pytest.mark.parametrize(
    ("snippet", "old", "new", "reported"),
    [
        (REFERENCE, "*Foam::sqr(Foam::sin(pi*c.z()));", "*Foam::sin(pi*c.z());", "field F"),
        (REFERENCE, "1.0 + c.x()*Foam::sqr(c.y())", "1.0 + c.x()*c.y()", "field G"),
        (REFERENCE, "u2[cellI] = inv1t*Foam::pow(G, -0.5)", "u2[cellI] = inv1t*Foam::pow(G, 0.5)", "exact u2"),
        (REFERENCE, "(K.xy() + K.yx())*dx*dy*sz2", "K.xy()*dx*dy*sz2", "source"),
        (REFERENCE, "(K.xz() + K.zx())*dx*sy2*dz", "(K.xz() + K.zx())*dx*sy2*dy", "source"),
        (REFERENCE, "sqrt1t*(beta*F - divKGradF)", "sqrt1t*(beta*F + divKGradF)", "source"),
        (REFERENCE, "dzz = 2.0*piSqr*", "dzz = piSqr*", "source"),
        (ELECTRO, "0.106875 -0.0084931 -0.022561 0.116682", "0.106875 -0.022561 -0.0084931 0.116682", "conductivity"),
        (ELECTRO, "] 3;", "] 4;", "electroProperties chi/cm"),
        (ELECTRO, "manufacturedAnisotropicMonodomainVerifier", "manufacturedFDAMonodomainVerifier", "verifier type"),
        (ELECTRO, '"3D"', '"2D"', "dimension"),
        (VERIFIER, "model.geometricDimension() != 3", "model.geometricDimension() != 2", "verifier configuration"),
        (VERIFIER, "vector::one", "vector(2, 2, 2)", "verifier domain"),
        (VERIFIER, "& centres = mesh.C()", "& centres = mesh.Cf()", "norm points"),
        (VERIFIER, "u2Norms =", "u3Norms =", "norm fields"),
        (SWEEP, "0.0398782", "0.0398", "hex conductivity"),
        (SWEEP, "0.000140174", "0.000140", "hex refinement"),
        (TET_SWEEP, "-0.0130256", "-0.0130", "tet conductivity"),
        (TET_SWEEP, "0.000560538", "0.00056", "tet refinement"),
        (fda.TET_GEO, "(lc = 1/N)", "(lc = 2/N)", "tet mesh size"),
        (fda.IONIC, "CONSTANTS[Beta] = -8.6", "CONSTANTS[Beta] = -8.7", "ionic Beta"),
        (fda.IONIC, "pow(STATES[u2], 3)", "pow(STATES[u2], 2)", "rate u2"),
    ],
)
def test_a_changed_snippet_is_reported(snippet, old, new, reported):
    snippets = _snippets()
    assert old in snippets[snippet]
    snippets[snippet] = snippets[snippet].replace(old, new, 1)
    assert drift(snippets, load_problem("anisotropic_monodomain")) == [reported]


@pytest.mark.parametrize(
    ("block", "key", "value", "reported"),
    [
        ("parameters", "sigma_xy", 0.0084931, "conductivity"),
        ("parameters", "Beta", -8.7, "ionic Beta"),
        ("native", "cardiacfoam", {"commit": "277dfeb1933990da366d4b30dd9ef40b3e94c87c", "ionic_model": "x",
                                   "verification_model": "manufacturedAnisotropicMonodomainVerifier",
                                   "record": "r"}, "verifier configuration"),
    ],
)
def test_a_changed_datum_is_reported(block, key, value, reported):
    problem = load_problem("anisotropic_monodomain")
    problem[block][key] = value
    assert reported in drift(_snippets(), problem)
