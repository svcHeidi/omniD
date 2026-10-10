"""Gate 2: the problem's data equals what cardiacFOAM's code states, read from verbatim snippets of that code.

A change to the owner's C++ or case files that the data does not follow fails here, once the snippets are
refreshed from the new commit.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

sympy = pytest.importorskip("sympy")

from omnidriver.verifier.problem import load_problem, pde_sides

FIXTURES = Path(__file__).parent / "fixtures" / "cardiacfoam"
IONIC = "src/ionicModels/verificationModels/monodomainFDAManufactured/monodomainFDAManufactured_2014.H"
IONIC_CURRENT = "src/ionicModels/verificationModels/monodomainFDAManufactured/monodomainFDAManufactured.C"
SOLVER = "src/electroModels/myocardiumModels/monodomainSolver/monodomainSolver.C"
DOMAIN = "src/electroModels/electroDomains/myocardiumDomain/myocardiumDomain.C"
WALL = "src/electroModels/electroDomains/myocardiumDomain/sealedWall/conormalZeroFluxFvPatchScalarField.C"
REFERENCE = "src/verificationModels/monodomainVerification/manufacturedFDAReference.H"
VERIFIER = "src/verificationModels/monodomainVerification/manufacturedFDAMonodomainVerifier.C"
UTILS = "src/verificationModels/verificationUtils.H"
CASE = "tutorials/manufacturedSolutions/monodomainPseudoECG"
ELECTRO = f"{CASE}/constant/electroProperties"
CONTROL = f"{CASE}/system/controlDict"
BLOCKMESH = {d: f"{CASE}/system/blockMeshDict.{d}D" for d in (1, 2, 3)}
SWEEP = f"{CASE}/setup/studies/cartesianConvergence/sweep_hex_convergence.json"
TET_SWEEP = f"{CASE}/setup/studies/tetConvergence/sweep_tet_generic.json"
TET_GEO = f"{CASE}/setup/studies/tetConvergence/box.geo.template"
TEMPORAL_SWEEP = f"{CASE}/setup/studies/temporalConvergence/sweep_temporal_convergence.json"
SNIPPETS = (IONIC, IONIC_CURRENT, SOLVER, DOMAIN, WALL, REFERENCE, VERIFIER, UTILS, ELECTRO, CONTROL, SWEEP,
            TET_SWEEP, TET_GEO, TEMPORAL_SWEEP, *BLOCKMESH.values())

# The C++ names its constants and state indices; the data names them so.
CXX_NAMES = {"Chi": "chi", "Fx": "F", "Gx": "G"}
# Each term of the solver's equation, in the data's PDE syntax.
CXX_PDE_TERMS = {
    "fvm::ddt(domain.VmRef())": "Derivative(V, t)",
    "fvm::laplacian(tGf(), domain.Vm())": "div(sigma*grad(V))",
    "domain.chi()": "chi",
    "domain.Cm()": "Cm",
    "tIionExtrap()": "Im",
    "domain.sourceField()": "source",
}
# The domain current Im the cell model hands the solver. Its correction is zero here: only the coupled 1D-3D
# verifier sets a manufactured source term on the ionic model.
CXX_IM_TERMS = {
    "Im[integrationPtI]": "Im",
    "A[Iion]": "Iion",
    "CONSTANTS_[Cm]": "Cm",
    "manufacturedSourceCorrection(integrationPtI)": "0",
}
CXX_REPORT_TERMS = {"time.endTime().value()": "end", "time.deltaTValue()": "dt", "time.value()": "t"}
# sealedWallTrace, through conormalWallPatchTypes, to the patch type every non-constraint patch takes.
CXX_WALL_TRACES = {"zeroGradient": "zero_normal_gradient"}
CXX_POINTS = {"C()": "cell_centres"}
# The time the exact fields are evaluated at: the mesh time, reached after a level's steps.
CXX_NORM_TIMES = {"mesh.time().value()": "steps*dt"}
CXX_NORM_KINDS = {"L1": "weightedAbs/totalVolume", "L2": "Foam::sqrt(weightedSq/totalVolume)", "Linf": "maxAbs"}
CXX_NORM_WEIGHTS = {"cell_volume": ("weightedAbs += volumes[i]*diff;", "weightedSq += volumes[i]*diff*diff;")}
CXX_NORM_NORMALISATIONS = {"total_volume": "totalVolume += volumes[i];"}
CXX_FIELDS = {"Vm": "V"}
# OpenFOAM's dimension sets [kg m s K mol A cd], in SI units.
SI_UNITS = {(0, -1, 0, 0, 0, 0, 0): "1/m", (-1, -4, 4, 0, 0, 2, 0): "F/m^2", (-1, -3, 3, 0, 0, 2, 0): "S/m"}
# What the cell model's current is per, from its dimensions: Cm times the domain current Im (Im = A[Iion]/Cm).
CURRENT_BASES = {"dimCurrent/dimArea": "per_unit_membrane_area", "dimVoltage/dimTime": "per_unit_capacitance"}


def _snippets() -> dict[str, str]:
    return {name: (FIXTURES / name).read_text() for name in SNIPPETS}


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


def _spelled(text: str, terms: dict[str, str]) -> str:
    text = " ".join(text.split())
    for cxx, data in terms.items():
        text = text.replace(cxx, data)
    return text


def _equation(lhs: str, rhs: str) -> object | None:
    """``lhs - rhs`` with each operator an opaque function, or None when a side is not in the data's syntax."""
    opaque = {name: sympy.Function(name) for name in ("Derivative", "div", "grad")}
    try:
        return sympy.expand(_sym(lhs, opaque) - _sym(rhs, opaque))
    except (SyntaxError, TypeError, sympy.SympifyError):
        return None


def _pde_drift(snippets: dict[str, str], problem: dict, commit: str) -> list[str]:
    function, *solve = _body(snippets[SOLVER], commit)
    lhs, rhs = _spelled(" ".join(solve), CXX_PDE_TERMS).split("==")
    ((im, current),) = _statements([_spelled(" ".join(_body(snippets[IONIC_CURRENT], commit)), CXX_IM_TERMS)])
    native = _equation(lhs, rhs)
    data = _equation(*pde_sides(problem["pde"]["equation"]))
    found = []
    if native is None or data is None or sympy.simplify(native.subs(sympy.Symbol(im), _sym(current, {})) - data):
        found.append("pde")
    algorithm = next(line for line in _body(snippets[ELECTRO], commit) if "solutionAlgorithm" in line)
    if not function.endswith("solveDiffusion" + algorithm.split()[-1].rstrip(";").capitalize()):
        found.append("solution algorithm")
    return found


def _units_drift(snippets: dict[str, str], problem: dict, commit: str) -> list[str]:
    found = []
    units = problem["units"]["native"]
    electro = [line.split() for line in _body(snippets[ELECTRO], commit)]
    for line in electro:
        if "[" in line:
            name = {"cm": "Cm"}.get(line[0], line[0])
            exponents = tuple(int(v) for v in " ".join(line).split("[")[1].split("]")[0].split())
            if SI_UNITS.get(exponents) != units[name]:
                found.append(f"units {name}")
    conductivity = _body(snippets[SWEEP], commit)[0]
    exponents = tuple(int(v) for v in conductivity.split("[")[1].split("]")[0].split())
    if SI_UNITS.get(exponents) != units["sigma"]:
        found.append("units sigma")

    current_dims, chi_dims, cm_dims = (
        re.search(pattern, " ".join(_body(snippets[DOMAIN], commit))).group(1)
        for pattern in (r'"ionicCurrent",.*?dimensionedScalar\("zero", ([\w/*()]+), 0\.0\)',
                        r'chi_\("chi", ([\w/*()]+),', r'Cm_\("cm", ([\w/*()]+),')
    )
    dims = {name: sympy.Symbol(name) for name in ("dimCurrent", "dimTime", "dimVoltage", "dimArea", "dimVolume")}
    iion = sympy.simplify(_sym(cm_dims, dims) * _sym(current_dims, dims))
    basis = next((value for key, value in CURRENT_BASES.items() if sympy.simplify(iion - _sym(key, dims)) == 0), None)
    if basis != problem["units"]["Iion"]:
        found.append("units Iion")
    if sympy.simplify(_sym(chi_dims, dims) - dims["dimArea"] / dims["dimVolume"]) != 0:
        found.append("units chi")
    return found


def _boundary_drift(snippets: dict[str, str], problem: dict, commit: str) -> list[str]:
    electro = {line.split()[0]: line.split()[-1].rstrip(";") for line in _body(snippets[ELECTRO], commit)}
    wall = " ".join(" ".join(_body(snippets[WALL], commit)).split())
    trace = electro["sealedWallTrace"]
    physical = f': word("{trace}")' in wall and "constraintType(t) ? t : physicalType" in wall
    if (electro["sealedHeartBoundary"] != "false" or not physical
            or CXX_WALL_TRACES.get(trace) != problem["boundary"]["all_faces"]):
        return ["boundary"]
    return []


def _domain_drift(snippets: dict[str, str], problem: dict, commit: str) -> list[str]:
    found = []
    box = problem["domain"]["box"]
    for d, name in BLOCKMESH.items():
        vertices = [tuple(float(v) for v in line.strip(" ()").split()) for line in _body(snippets[name], commit)]
        extents = [[min(v[axis] for v in vertices), max(v[axis] for v in vertices)] for axis in range(3)]
        if extents[:d] != box[:d]:
            found.append(f"domain {d}D")
    return found


def _time_drift(snippets: dict[str, str], problem: dict, commit: str) -> list[str]:
    found = []
    utils = _body(snippets[UTILS], commit)
    rule = _spelled(utils[0].strip().removeprefix("return").rstrip(";"), CXX_REPORT_TERMS)
    native_lhs, native_rhs = rule.split(">=")
    data_lhs, data_rhs = problem["time"]["report_when"].split(">=")
    if not _same(f"({native_lhs}) - ({native_rhs})", f"({data_lhs}) - ({data_rhs})"):
        found.append("report rule")
    (end_time,) = _body(snippets[CONTROL], commit)
    if float(end_time.split()[-1].rstrip(";")) != problem["time"]["end"]:
        found.append("endTime")
    return found


def _norms_drift(snippets: dict[str, str], problem: dict, commit: str) -> list[str]:
    found = []
    norms = problem["norms"]
    utils = " ".join(" ".join(_body(snippets[UTILS], commit)).split())
    for kind in norms["kinds"]:
        if CXX_NORM_KINDS[kind] not in utils:
            found.append(f"norm {kind}")
    if not all(line in utils for line in CXX_NORM_WEIGHTS[norms["weight"]]):
        found.append("norm weight")
    if CXX_NORM_NORMALISATIONS[norms["normalised_by"]] not in utils:
        found.append("norm normalisation")

    verifier = _body(snippets[VERIFIER], commit)
    centres = [line for line in verifier if "centres =" in line]
    times = [line.split("=")[1].strip().rstrip(";") for line in verifier if "const scalar t =" in line]
    pre_points, post_points = (CXX_POINTS.get(line.split(".")[-2]) for line in centres)
    if post_points != norms["points"]:
        found.append("norm points")
    if pre_points != problem["initial"]["points"]["cardiacfoam"]:
        found.append("initial points")
    if CXX_NORM_TIMES.get(times[1]) != norms["at"]:
        found.append("norm time")
    fields = [CXX_FIELDS.get(m, m) for m in re.findall(r"const auto (\w+)Norms =", " ".join(verifier))]
    if fields != norms["fields"]:
        found.append("norm fields")
    return found


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
    # The cell model leaves V to the PDE: its rate is pinned to zero.
    unknown = problem["pde"]["unknown"]
    if float(constants[f"RATES[{unknown}]"]) != 0 or problem["cell_model"]["inputs"] != [unknown]:
        found.append("cell model integrates V")
    rates = problem["cell_model"]["rates"]
    for state in problem["cell_model"]["states"]:
        if not _same(constants[f"RATES[{state}]"], rates[state]):
            found.append(f"rate {state}")
    if not _same(constants["ALGEBRAIC[Iion]"], problem["cell_model"]["Iion"]):
        found.append("Iion")
    found += _pde_drift(snippets, problem, commit)
    found += _units_drift(snippets, problem, commit)
    found += _boundary_drift(snippets, problem, commit)
    found += _domain_drift(snippets, problem, commit)

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

    electro = {line.split()[0]: line.split()[-1].rstrip(";") for line in _body(snippets[ELECTRO], commit)}
    if (float(electro["chi"]), float(electro["cm"])) != (problem["parameters"]["chi"], problem["parameters"]["Cm"]):
        found.append("electroProperties chi/cm")
    found += _time_drift(snippets, problem, commit)
    found += _norms_drift(snippets, problem, commit)

    conductivity, *ladder = _body(snippets[SWEEP], commit)
    xx, _, _, yy, _, zz = (float(v) for v in conductivity.split("(")[1].split(")")[0].split())
    parameters = problem["parameters"]
    if (xx, yy, zz) != (parameters["sigma_xx"], parameters["sigma_yy"], parameters["sigma_zz"]):
        found.append("conductivity")
    values = [float(line) for line in ladder]
    hex_ladder = problem["refinement"]["hex"]
    if values != [*hex_ladder["cells_per_axis"], *hex_ladder["dt"]]:
        found.append("hex refinement")
    found += _tet_drift(snippets, problem, commit)
    found += _temporal_drift(snippets, problem, commit)
    return found


def _temporal_drift(snippets: dict[str, str], problem: dict, commit: str) -> list[str]:
    """The temporal study's rows, one per (dimension, cell count, dt), against the temporal ladder and the
    dimensions it excludes."""
    values = [line.strip().strip('",') for line in _body(snippets[TEMPORAL_SWEEP], commit)]
    count = len(values) // 3
    rows = list(zip((int(v.removesuffix("D")) for v in values[:count]), map(int, values[count:2 * count]),
                    map(float, values[2 * count:])))
    temporal = problem["refinement"]["temporal"]
    expected = [(d, temporal["cells_per_axis"][str(d)], dt) for d in temporal["dimensions"] for dt in temporal["dt"]]
    expected += [(int(d), entry["cells_per_axis"], dt)
                 for d, entry in temporal.get("excluded", {}).items() for dt in entry["dt"]]
    return [] if sorted(rows) == sorted(expected) else ["temporal refinement"]


def _tet_drift(snippets: dict[str, str], problem: dict, commit: str) -> list[str]:
    """The tet study's FDA rows (its first four, one per level) against the tet ladder; its mesh size against the
    spacing the ladder implies, lc = edge/cells_per_axis."""
    dimension, conductivity, verifier, *ladder = _body(snippets[TET_SWEEP], commit)
    tet = problem["refinement"]["tet"]
    parameters = problem["parameters"]
    found = []
    if [int(dimension.strip().strip('"').removesuffix("D"))] != tet["dimensions"]:
        found.append("tet dimensions")
    xx, _, _, yy, _, zz = (float(v) for v in conductivity.split("(")[1].split(")")[0].split())
    if (xx, yy, zz) != (parameters["sigma_xx"], parameters["sigma_yy"], parameters["sigma_zz"]):
        found.append("tet conductivity")
    if verifier.strip().strip('",') != problem["native"]["cardiacfoam"]["verification_model"]:
        found.append("tet verifier")
    if [float(line) for line in ladder] != [*tet["cells_per_axis"], *tet["dt"]]:
        found.append("tet refinement")
    geo = " ".join(_body(snippets[TET_GEO], commit))
    edge = problem["domain"]["box"][0][1] - problem["domain"]["box"][0][0]
    if (edge != 1 or "(lc = 1/N)" not in geo
            or not all(f"Mesh.MeshSize{bound} = lc;" in geo for bound in ("Min", "Max"))):
        found.append("tet mesh size")
    return found


def test_the_problem_data_matches_cardiacfoam():
    assert drift(_snippets(), load_problem("fda_monodomain")) == []


@pytest.mark.parametrize(
    ("snippet", "old", "new", "reported"),
    [
        (IONIC, "CONSTANTS[Cm]  = 2.0", "CONSTANTS[Cm]  = 2.5", "ionic Cm"),
        (IONIC, "CONSTANTS[Beta] = -8.6", "CONSTANTS[Beta] = -8.7", "ionic Beta"),
        (IONIC, "RATES[V] = 0.0", "RATES[V] = 1.0", "cell model integrates V"),
        (IONIC, "pow(STATES[u2], 3)", "pow(STATES[u2], 2)", "rate u2"),
        (IONIC, "/ CONSTANTS[Chi]", "* CONSTANTS[Chi]", "Iion"),
        (SOLVER, "+ domain.sourceField()", "- domain.sourceField()", "pde"),
        (SOLVER, "- domain.chi()*domain.Cm()*tIionExtrap()", "- domain.chi()*tIionExtrap()", "pde"),
        (SOLVER, "fvm::laplacian(tGf(), domain.Vm())", "fvm::laplacian(tGf(), domain.Vm())/domain.chi()", "pde"),
        (SOLVER, "solveDiffusionImplicit", "solveDiffusionExplicit", "solution algorithm"),
        (IONIC_CURRENT, "A[Iion]/CONSTANTS_[Cm]", "A[Iion]", "pde"),
        (DOMAIN, "dimVoltage/dimTime", "dimCurrent/dimArea", "units Iion"),
        (DOMAIN, '"chi", dimArea/dimVolume', '"chi", dimArea', "units chi"),
        (ELECTRO, "[ -1 -4 4 0 0 2 0 ]", "[ -1 -2 4 0 0 2 0 ]", "units Cm"),
        (ELECTRO, "zeroGradient;", "conormal;", "boundary"),
        (WALL, ': word("zeroGradient")', ': word("fixedValue")', "boundary"),
        (WALL, "? t : physicalType", "? t : word(\"fixedValue\")", "boundary"),
        (BLOCKMESH[2], "(1 1 0)", "(1 2 0)", "domain 2D"),
        (REFERENCE, "cos(3.0*", "cos(4.0*", "field F 3D"),
        (REFERENCE, "Foam::pow(Gx[i], -0.5)", "Foam::pow(Gx[i], 0.5)", "exact u2"),
        (ELECTRO, "] 3;", "] 4;", "electroProperties chi/cm"),
        (CONTROL, "0.2;", "0.3;", "endTime"),
        (UTILS, "0.5*time.deltaTValue()", "time.deltaTValue()", "report rule"),
        (UTILS, "Foam::sqrt(weightedSq/totalVolume)", "Foam::sqrt(weightedSq)", "norm L2"),
        (UTILS, "weightedAbs += volumes[i]*diff;", "weightedAbs += diff;", "norm weight"),
        (UTILS, "totalVolume += volumes[i];", "totalVolume += 1;", "norm normalisation"),
        (VERIFIER, "& centres = mesh.C()", "& centres = mesh.Cf()", "norm points"),
        (VERIFIER, "& centres = Vm.mesh().C()", "& centres = Vm.mesh().Cf()", "initial points"),
        (VERIFIER, "t = mesh.time().value()", "t = mesh.time().endTime().value()", "norm time"),
        (VERIFIER, "u2Norms =", "u3Norms =", "norm fields"),
        (SWEEP, "0.121585420", "0.121585", "conductivity"),
        (SWEEP, "0.000140174", "0.000140", "hex refinement"),
        (TET_SWEEP, '"3D"', '"2D"', "tet dimensions"),
        (TET_SWEEP, "0.030396355", "0.0398782", "tet conductivity"),
        (TET_SWEEP, "manufacturedFDAMonodomainVerifier", "manufacturedAnisotropicMonodomainVerifier", "tet verifier"),
        (TET_SWEEP, "0.000560538", "0.00056", "tet refinement"),
        (TEMPORAL_SWEEP, "0.000280269", "0.00028", "temporal refinement"),
        (TEMPORAL_SWEEP, "        640,", "        320,", "temporal refinement"),
        (TEMPORAL_SWEEP, "        160,", "        80,", "temporal refinement"),
        (TET_GEO, "(lc = 1/N)", "(lc = 2/N)", "tet mesh size"),
        (TET_GEO, "MeshSizeMax = lc;", "MeshSizeMax = 2*lc;", "tet mesh size"),
    ],
)
def test_a_changed_snippet_is_reported(snippet, old, new, reported):
    snippets = _snippets()
    assert old in snippets[snippet]
    snippets[snippet] = snippets[snippet].replace(old, new, 1)
    assert drift(snippets, load_problem("fda_monodomain")) == [reported]


@pytest.mark.parametrize(
    ("block", "key", "value", "reported"),
    [
        ("pde", "equation", "chi*Cm*(Derivative(V, t) + Iion) - div(sigma*grad(V)) = source", "pde"),
        ("units", "Iion", "per_unit_capacitance", "units Iion"),
        ("time", "report_when", "t + dt >= end", "report rule"),
        ("norms", "points", "nodes", "norm points"),
        ("domain", "box", [[0, 1], [0, 2], [0, 1]], "domain 2D"),
    ],
)
def test_a_changed_datum_is_reported(block, key, value, reported):
    problem = load_problem("fda_monodomain")
    problem[block][key] = value
    assert reported in drift(_snippets(), problem)
