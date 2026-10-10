"""The problem library: each manufactured problem is one TOML file under ``problems/``, validated on load."""
from __future__ import annotations

import ast
import tomllib
from importlib.resources import files
from typing import Any, Iterable, Mapping

from omnidriver.core.refusal import Refusal

#: Each equation the residual check knows, and the parameters its form names.
EQUATIONS: dict[str, tuple[str, ...]] = {"monodomain": ("Cm", "chi", "sigma_xx", "sigma_yy", "sigma_zz")}
BOUNDARY_KINDS = ("zero_normal_gradient",)
INITIAL_KINDS = ("exact",)
MESH_KINDS = ("hex",)
#: Which value of a derived constant a solver is given: the native literal, or the value derived from the data.
DERIVED_USES = ("native", "derived")

FUNCTIONS = frozenset({"sqrt", "cos", "sin", "exp", "log"})
CONSTANTS = frozenset({"pi"})
SPACE = ("x", "y", "z")
TIME = "t"
POTENTIAL = "V"

_BLOCKS: dict[str, frozenset[str] | None] = {
    "id": None, "title": None, "equation": None, "dimensions": None, "mesh_progression": None, "cites": None,
    "native": None, "domain": frozenset({"box"}), "time": frozenset({"start", "end"}), "parameters": None,
    "derived": None, "fields": None, "exact": None, "cell_model": frozenset({"states", "rates", "Iion"}),
    "source": frozenset({"expression"}), "boundary": frozenset({"all_faces"}), "initial": frozenset({"fields"}),
    "refinement": None, "norms": frozenset({"fields", "kinds", "points", "weight", "normalised_by", "at"}),
    "provenance": None,
}
_DERIVED_KEYS = frozenset({"expression", "native", "use", "use_reason", "tolerance", "tolerance_reason"})
_TRACED = ("equation", "domain", "time", "parameters", "derived", "fields", "exact", "cell_model", "source",
           "boundary", "initial", "refinement", "norms")
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


def validate_problem(problem: Mapping[str, Any]) -> None:
    """Refuse a definition with an unknown or missing key, an off-menu kind, a per-dimension map that misses a
    dimension, an expression that does not parse or names a symbol out of its scope, or a block with no source."""
    _keys("", problem, frozenset(_BLOCKS), required=True)
    for name, keys in _BLOCKS.items():
        if keys is not None:
            _keys(f"{name}.", _table(name, problem[name]), keys, required=True)
    _menu("equation", problem["equation"], tuple(EQUATIONS))
    _menu("boundary.all_faces", problem["boundary"]["all_faces"], BOUNDARY_KINDS)
    _menu("initial.fields", problem["initial"]["fields"], INITIAL_KINDS)
    for kind in problem["mesh_progression"]:
        _menu("mesh_progression", kind, MESH_KINDS)
    dimensions = problem["dimensions"]
    if not dimensions or any(d not in (1, 2, 3) for d in dimensions):
        raise ProblemError(f"dimensions: {dimensions!r} is not a non-empty subset of [1, 2, 3]")

    parameters = _table("parameters", problem["parameters"])
    for name, value in parameters.items():
        if not isinstance(value, (int, float)):
            raise ProblemError(f"parameters.{name}: {value!r} is not a number")
    missing = [name for name in EQUATIONS[problem["equation"]] if name not in parameters]
    if missing:
        raise ProblemError(f"parameters: the {problem['equation']} equation needs {missing}")
    space = SPACE[:max(dimensions)]
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
            if not isinstance(entry[reason], str) or not entry[reason]:
                raise ProblemError(f"derived.{name}.{reason}: states no reason")
    fields = _table("fields", problem["fields"])
    for name, by_dimension in fields.items():
        _per_dimension(f"fields.{name}", by_dimension, dimensions, {*space, *parameters})

    cell = problem["cell_model"]
    states = list(cell["states"])
    exact = _table("exact", problem["exact"])
    if set(exact) != {POTENTIAL, *states}:
        raise ProblemError(f"exact: names {sorted(exact)}, but the unknowns are {[POTENTIAL, *states]}")
    solution_scope = {*space, TIME, *parameters, *derived, *fields}
    for name, text in exact.items():
        _expression(f"exact.{name}", text, solution_scope)
    _expression("source.expression", problem["source"]["expression"], solution_scope)
    rates = _table("cell_model.rates", cell["rates"])
    if set(rates) != set(states):
        raise ProblemError(f"cell_model.rates: names {sorted(rates)}, but the states are {states}")
    cell_scope = {POTENTIAL, *states, *parameters, *derived}
    for name, text in rates.items():
        _expression(f"cell_model.rates.{name}", text, cell_scope)
    _expression("cell_model.Iion", cell["Iion"], cell_scope)

    refinement = _table("refinement", problem["refinement"])
    if set(refinement) != set(problem["mesh_progression"]):
        raise ProblemError(f"refinement: has {sorted(refinement)}, the progression is {problem['mesh_progression']}")
    for kind, ladder in refinement.items():
        _keys(f"refinement.{kind}.", _table(f"refinement.{kind}", ladder), frozenset({"cells", "dt"}), required=True)
        if not ladder["cells"] or len(ladder["cells"]) != len(ladder["dt"]):
            raise ProblemError(f"refinement.{kind}: cells and dt must be non-empty and of equal length")

    provenance = _table("provenance", problem["provenance"])
    _keys("provenance.", provenance, frozenset(_TRACED), required=True)
    for name, sources in provenance.items():
        if not sources or not all(isinstance(source, str) and source for source in sources):
            raise ProblemError(f"provenance.{name}: names no source")


def _library():
    return files("omnidriver.verifier").joinpath("problems")


def _table(where: str, value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProblemError(f"{where}: expected a table, got {type(value).__name__}")
    return value


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


def _expression(where: str, text: Any, scope: Iterable[str]) -> None:
    if not isinstance(text, str):
        raise ProblemError(f"{where}: {text!r} is not an expression string")
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise ProblemError(f"{where}: {text!r} does not parse ({exc.msg})") from None
    allowed = {*scope, *CONSTANTS}
    callees = {id(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ProblemError(f"{where}: {type(node).__name__} is not allowed in an expression")
        if isinstance(node, ast.Call) and not (isinstance(node.func, ast.Name) and node.func.id in FUNCTIONS
                                               and not node.keywords):
            raise ProblemError(f"{where}: only {sorted(FUNCTIONS)} may be called")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float)):
            raise ProblemError(f"{where}: {node.value!r} is not a number")
        if isinstance(node, ast.Name) and id(node) not in callees and node.id not in allowed:
            raise ProblemError(f"{where}: {node.id!r} is not in scope here ({sorted(allowed)})")
