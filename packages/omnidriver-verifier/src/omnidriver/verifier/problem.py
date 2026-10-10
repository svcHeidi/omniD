"""The problem library: each manufactured problem is one TOML file under ``problems/``, validated on load."""
from __future__ import annotations

import ast
import math
import tomllib
from importlib.resources import files
from typing import Any, Iterable, Mapping

from omnidriver.core.refusal import Refusal

EQUATIONS = ("monodomain",)
BOUNDARY_KINDS = ("zero_normal_gradient",)
INITIAL_KINDS = ("exact",)
INITIAL_TIMES = ("start",)
MESH_KINDS = ("hex",)
#: Where a solver holds its unknowns, and so where an exact field is evaluated against it.
POINTS = ("cell_centres", "nodes")
#: Which value of a derived constant a solver is given: the native literal, or the value derived from the data.
DERIVED_USES = ("native", "derived")
UNIT_SYSTEMS = ("dimensionless",)
#: What the cell model's current is per: the PDE form decides it.
CURRENT_BASES = ("per_unit_membrane_area", "per_unit_capacitance")
DIMENSION_RULES = ("first_d_intervals",)
TENSOR_KINDS = ("diagonal",)
NORM_KINDS = ("L1", "L2", "Linf")
NORM_WEIGHTS = ("cell_volume",)
NORM_NORMALISATIONS = ("total_volume",)
#: When a level is judged: after its ``steps`` steps of ``dt``, the first time ``time.report_when`` holds.
NORM_TIMES = ("steps*dt",)
#: How each level's ``dt`` scales with its spacing ``h``, the box edge over ``cells_per_axis``.
DT_SCALINGS = {"h": 1, "h**2": 2}
#: The names a report rule may use: the time reached, the step and the end time.
REPORT_SCOPE = frozenset({"t", "dt", "end"})

FUNCTIONS = frozenset({"sqrt", "cos", "sin", "exp", "log"})
#: The differential operators a PDE may name: ``Derivative(f, t)``, ``grad(f)``, ``div(v)``.
OPERATORS = frozenset({"Derivative", "grad", "div"})
CONSTANTS = frozenset({"pi"})
SPACE = ("x", "y", "z")
TIME = "t"
#: The PDE's name for the cell model's current and for the source on its right-hand side.
CURRENT = "Iion"
SOURCE = "source"

_BLOCKS: dict[str, frozenset[str] | None] = {
    "id": None, "title": None, "equation": None, "dimensions": None, "mesh_progression": None, "cites": None,
    "native": None, "pde": frozenset({"equation", "unknown", "parameters", "tensors"}),
    "units": frozenset({"system", "system_reason", "native", "Iion", "Iion_reason", "fixed_capacitance"}),
    "domain": frozenset({"box", "dimension_d_uses"}), "time": frozenset({"start", "end", "report_when"}),
    "parameters": None,
    "derived": None, "fields": None, "exact": None,
    "cell_model": frozenset({"inputs", "states", "parameters", "shares_with_pde", "rates", "Iion"}),
    "source": frozenset({"expression"}), "boundary": frozenset({"all_faces"}),
    "initial": frozenset({"fields", "time", "points"}),
    "refinement": None, "norms": frozenset({"fields", "kinds", "points", "weight", "normalised_by", "at"}),
    "provenance": None,
}
_DERIVED_KEYS = frozenset({"expression", "native", "use", "use_reason", "tolerance", "tolerance_reason"})
_TRACED = ("pde", "units", "domain", "time", "parameters", "derived", "fields", "exact", "cell_model", "source",
           "boundary", "initial", "refinement", "norms")
# The owner's ladder departs from an exact h**2 scaling by 0.45% between its two coarsest levels.
_LADDER_SCALING_TOLERANCE = 0.01
_ALLOWED_NODES = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Call, ast.Name, ast.Load, ast.Constant,
                  ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.USub, ast.UAdd)


class ProblemError(Refusal):
    """A problem id the library does not hold (``unknown_problem``), or a problem file that breaks the schema
    (``problem_invalid``)."""

    def __init__(self, message: str, *, code: str = "problem_invalid") -> None:
        super().__init__(message)
        self.code = code


def problem_ids() -> list[str]:
    """The id of every problem the library holds, sorted."""
    return sorted(entry.name.removesuffix(".toml") for entry in _library().iterdir() if entry.name.endswith(".toml"))


def load_problem(problem_id: str) -> dict[str, Any]:
    """The validated definition of ``problem_id``; :class:`ProblemError` when it is unknown or invalid."""
    if problem_id not in problem_ids():
        raise ProblemError(f"no problem {problem_id!r}; the library holds {problem_ids()}", code="unknown_problem")
    problem = tomllib.loads(_library().joinpath(f"{problem_id}.toml").read_text())
    validate_problem(problem)
    if problem["id"] != problem_id:
        raise ProblemError(f"problems/{problem_id}.toml names itself {problem['id']!r}")
    return problem


def pde_sides(equation: str) -> tuple[str, str]:
    """The left- and right-hand side of a PDE written ``lhs = rhs``."""
    lhs, separator, rhs = equation.partition("=")
    if not separator or "=" in rhs:
        raise ProblemError(f"pde.equation: {equation!r} is not one 'lhs = rhs'")
    return lhs.strip(), rhs.strip()


def validate_problem(problem: Mapping[str, Any]) -> None:
    """Refuse a definition with an unknown or missing key, an off-menu kind, a per-dimension map that misses a
    dimension, an expression that does not parse or names a symbol out of its scope, a declared name list that is
    not the one its expressions use, or a block with no source."""
    _keys("", problem, frozenset(_BLOCKS), required=True)
    for name, keys in _BLOCKS.items():
        if keys is not None:
            _keys(f"{name}.", _table(name, problem[name]), keys, required=True)
    _menu("equation", problem["equation"], EQUATIONS)
    _menu("boundary.all_faces", problem["boundary"]["all_faces"], BOUNDARY_KINDS)
    _menu("initial.fields", problem["initial"]["fields"], INITIAL_KINDS)
    _menu("initial.time", problem["initial"]["time"], INITIAL_TIMES)
    for solver, points in _table("initial.points", problem["initial"]["points"]).items():
        _menu(f"initial.points.{solver}", points, POINTS)
    _menu("domain.dimension_d_uses", problem["domain"]["dimension_d_uses"], DIMENSION_RULES)
    for kind in problem["mesh_progression"]:
        _menu("mesh_progression", kind, MESH_KINDS)
    dimensions = problem["dimensions"]
    if not dimensions or any(d not in (1, 2, 3) for d in dimensions):
        raise ProblemError(f"dimensions: {dimensions!r} is not a non-empty subset of [1, 2, 3]")
    space = SPACE[:max(dimensions)]

    parameters = _table("parameters", problem["parameters"])
    for name, value in parameters.items():
        if not isinstance(value, (int, float)):
            raise ProblemError(f"parameters.{name}: {value!r} is not a number")
    derived = _table("derived", problem["derived"])
    for name, entry in derived.items():
        _keys(f"derived.{name}.", _table(f"derived.{name}", entry), _DERIVED_KEYS, required=True)
        _per_dimension(f"derived.{name}.expression", entry["expression"], dimensions, parameters)
        _per_dimension(f"derived.{name}.native", entry["native"], dimensions, None)
        _menu(f"derived.{name}.use", entry["use"], DERIVED_USES)
        tolerance = entry["tolerance"]
        if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)) or tolerance <= 0:
            raise ProblemError(f"derived.{name}.tolerance: {tolerance!r} is not a positive number")
        for reason in ("use_reason", "tolerance_reason"):
            _reason(f"derived.{name}.{reason}", entry[reason])
    fields = _table("fields", problem["fields"])
    for name, by_dimension in fields.items():
        _per_dimension(f"fields.{name}", by_dimension, dimensions, {*space, *parameters})

    pde = problem["pde"]
    tensors = _table("pde.tensors", pde["tensors"])
    for name, tensor in tensors.items():
        tensor = _table(f"pde.tensors.{name}", tensor)
        if len(tensor) != 1 or next(iter(tensor)) not in TENSOR_KINDS:
            raise ProblemError(f"pde.tensors.{name}: must be one of {list(TENSOR_KINDS)}")
        entries = tensor["diagonal"]
        if len(entries) < len(space) or any(entry not in parameters for entry in entries):
            raise ProblemError(f"pde.tensors.{name}: {entries} is not one parameter per axis {list(space)}")
    cell = problem["cell_model"]
    states = list(cell["states"])
    unknown = pde["unknown"]
    if unknown in states or unknown in parameters or unknown in SPACE or unknown == TIME:
        raise ProblemError(f"pde.unknown: {unknown!r} must name neither a state, a parameter nor a coordinate")
    lhs, rhs = pde_sides(_string("pde.equation", pde["equation"]))
    if rhs != SOURCE:
        raise ProblemError(f"pde.equation: the right-hand side must be {SOURCE!r}, not {rhs!r}")
    pde_scope = {unknown, CURRENT, TIME, *parameters, *tensors}
    used = _expression("pde.equation", lhs, pde_scope, OPERATORS)
    _declares("pde.parameters", pde["parameters"], used & {*parameters, *tensors})

    exact = _table("exact", problem["exact"])
    if set(exact) != {unknown, *states}:
        raise ProblemError(f"exact: names {sorted(exact)}, but the unknowns are {[unknown, *states]}")
    solution_scope = {*space, TIME, *parameters, *derived, *fields}
    for name, text in exact.items():
        _expression(f"exact.{name}", text, solution_scope)
    _expression("source.expression", problem["source"]["expression"], solution_scope)

    if list(cell["inputs"]) != [unknown]:
        raise ProblemError(f"cell_model.inputs: {cell['inputs']} must be the PDE's unknown [{unknown!r}]")
    rates = _table("cell_model.rates", cell["rates"])
    if set(rates) != set(states):
        raise ProblemError(f"cell_model.rates: names {sorted(rates)}, but the states are {states}")
    cell_scope = {unknown, *states, *parameters, *derived}
    used = set()
    for name, text in rates.items():
        used |= _expression(f"cell_model.rates.{name}", text, cell_scope)
    used |= _expression(f"cell_model.{CURRENT}", cell[CURRENT], cell_scope)
    _declares("cell_model.parameters", cell["parameters"], used & {*parameters, *derived})
    shared = set(cell["shares_with_pde"])
    if not shared <= set(cell["parameters"]) & set(pde["parameters"]):
        raise ProblemError(f"cell_model.shares_with_pde: {sorted(shared)} must be parameters of both the cell "
                           "model and the PDE")

    units = problem["units"]
    _menu("units.system", units["system"], UNIT_SYSTEMS)
    _menu("units.Iion", units["Iion"], CURRENT_BASES)
    for key in ("system_reason", "Iion_reason", "fixed_capacitance"):
        _reason(f"units.{key}", units[key])
    unit_names = _table("units.native", units["native"])
    stray = sorted(set(unit_names) - {*space, TIME, unknown, *parameters, *tensors})
    if stray or not all(isinstance(unit, str) and unit for unit in unit_names.values()):
        raise ProblemError(f"units.native: {stray or 'an empty unit'} names no coordinate, unknown or parameter")

    time = problem["time"]
    report_when = _rule("time.report_when", time["report_when"])
    refinement = _table("refinement", problem["refinement"])
    if set(refinement) != set(problem["mesh_progression"]):
        raise ProblemError(f"refinement: has {sorted(refinement)}, the progression is {problem['mesh_progression']}")
    for kind, ladder in refinement.items():
        _ladder(f"refinement.{kind}", _table(f"refinement.{kind}", ladder), time, report_when)

    norms = problem["norms"]
    _menu("norms.at", norms["at"], NORM_TIMES)
    _menu("norms.points", norms["points"], POINTS)
    _menu("norms.weight", norms["weight"], NORM_WEIGHTS)
    _menu("norms.normalised_by", norms["normalised_by"], NORM_NORMALISATIONS)
    for kind in norms["kinds"]:
        _menu("norms.kinds", kind, NORM_KINDS)
    if not norms["fields"] or not set(norms["fields"]) <= {unknown, *states}:
        raise ProblemError(f"norms.fields: {norms['fields']} must be unknowns of the problem ({[unknown, *states]})")

    provenance = _table("provenance", problem["provenance"])
    _keys("provenance.", provenance, frozenset(_TRACED), required=True)
    for name, sources in provenance.items():
        if not sources or not all(isinstance(source, str) and source for source in sources):
            raise ProblemError(f"provenance.{name}: names no source")


def _rule(where: str, text: Any) -> Any:
    """Refuse ``text`` unless it is one comparison of arithmetic over :data:`REPORT_SCOPE`; return it compiled."""
    text = _string(where, text)
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise ProblemError(f"{where}: {text!r} does not parse ({exc.msg})") from None
    if not (isinstance(tree.body, ast.Compare) and len(tree.body.ops) == 1
            and isinstance(tree.body.ops[0], (ast.GtE, ast.Gt))):
        raise ProblemError(f"{where}: {text!r} is not one comparison 'a >= b' or 'a > b'")
    for side in (tree.body.left, tree.body.comparators[0]):
        _expression(where, ast.unparse(side), REPORT_SCOPE)
    return compile(tree, where, "eval")


def _ladder(where: str, ladder: Mapping[str, Any], time: Mapping[str, Any], report_when: Any) -> None:
    _keys(f"{where}.", ladder, frozenset({"cells_per_axis", "dt", "steps", "dt_scales_as"}), required=True)
    cells, dts, steps = ladder["cells_per_axis"], ladder["dt"], ladder["steps"]
    if not cells or not len(cells) == len(dts) == len(steps):
        raise ProblemError(f"{where}: cells_per_axis, dt and steps must be non-empty and of equal length")
    for dt, given in zip(dts, steps):
        if isinstance(dt, bool) or not isinstance(dt, (int, float)) or dt <= 0:
            raise ProblemError(f"{where}.dt: {dt!r} is not a positive number")
        reported = _report_step(report_when, time, dt)
        if reported is None:
            raise ProblemError(f"time.report_when: dt = {dt} never meets it by the end time")
        if given != reported:
            raise ProblemError(f"{where}.steps: dt = {dt} first meets time.report_when after {reported} steps, "
                               f"not {given}")
    _menu(f"{where}.dt_scales_as", ladder["dt_scales_as"], tuple(DT_SCALINGS))
    power = DT_SCALINGS[ladder["dt_scales_as"]]
    for (coarse, coarse_dt), (fine, fine_dt) in zip(zip(cells, dts), zip(cells[1:], dts[1:])):
        expected = (fine / coarse) ** power
        if abs((coarse_dt / fine_dt) / expected - 1) > _LADDER_SCALING_TOLERANCE:
            raise ProblemError(f"{where}.dt_scales_as: dt {coarse_dt} -> {fine_dt} over {coarse} -> {fine} cells "
                               f"is not dt ~ {ladder['dt_scales_as']}")


def _report_step(report_when: Any, time: Mapping[str, Any], dt: float) -> int | None:
    last = math.ceil((time["end"] - time["start"]) / dt) + 1
    for steps in range(last + 1):
        # The rule was validated as arithmetic over REPORT_SCOPE, so eval sees nothing else.
        if eval(report_when, {"__builtins__": {}}, {"t": time["start"] + steps * dt, "dt": dt, "end": time["end"]}):
            return steps
    return None


def _library():
    return files("omnidriver.verifier").joinpath("problems")


def _table(where: str, value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProblemError(f"{where}: expected a table, got {type(value).__name__}")
    return value


def _string(where: str, value: Any) -> str:
    if not isinstance(value, str):
        raise ProblemError(f"{where}: {value!r} is not a string")
    return value


def _reason(where: str, value: Any) -> None:
    if not isinstance(value, str) or not value:
        raise ProblemError(f"{where}: states no reason")


def _keys(prefix: str, table: Mapping[str, Any], known: Iterable[str], *, required: bool) -> None:
    known = frozenset(known)
    unknown = sorted(set(table) - known)
    if unknown:
        raise ProblemError(f"unknown key(s) {', '.join(prefix + key for key in unknown)}")
    missing = sorted(known - set(table)) if required else []
    if missing:
        raise ProblemError(f"missing key(s) {', '.join(prefix + key for key in missing)}")


def _menu(where: str, value: Any, menu: tuple[str, ...]) -> None:
    if value not in menu:
        raise ProblemError(f"{where}: {value!r} is not one of {list(menu)}")


def _declares(where: str, declared: Any, used: set[str]) -> None:
    if not isinstance(declared, list) or len(set(declared)) != len(declared) or set(declared) != used:
        raise ProblemError(f"{where}: declares {declared!r}, but its expressions use {sorted(used)}")


def _per_dimension(where: str, value: Any, dimensions: list[int], scope: Iterable[str] | None) -> None:
    table = _table(where, value)
    if set(table) != {str(d) for d in dimensions}:
        raise ProblemError(f"{where}: has dimensions {sorted(table)}, the problem has {dimensions}")
    for dimension, item in table.items():
        if scope is None:
            if not isinstance(item, (int, float)):
                raise ProblemError(f"{where}.{dimension}: {item!r} is not a number")
        else:
            _expression(f"{where}.{dimension}", item, scope)


def _expression(where: str, text: Any, scope: Iterable[str], operators: frozenset[str] = frozenset()) -> set[str]:
    """Refuse ``text`` unless it is arithmetic over ``scope``; return the names it uses."""
    text = _string(where, text)
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise ProblemError(f"{where}: {text!r} does not parse ({exc.msg})") from None
    allowed = {*scope, *CONSTANTS}
    callable_names = FUNCTIONS | operators
    callees = {id(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}
    used = set()
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ProblemError(f"{where}: {type(node).__name__} is not allowed in an expression")
        if isinstance(node, ast.Call) and not (isinstance(node.func, ast.Name) and node.func.id in callable_names
                                               and not node.keywords):
            raise ProblemError(f"{where}: only {sorted(callable_names)} may be called")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float)):
            raise ProblemError(f"{where}: {node.value!r} is not a number")
        if isinstance(node, ast.Name) and id(node) not in callees:
            if node.id not in allowed:
                raise ProblemError(f"{where}: {node.id!r} is not in scope here ({sorted(allowed)})")
            used.add(node.id)
    return used
