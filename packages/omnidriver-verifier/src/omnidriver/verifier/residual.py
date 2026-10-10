"""Gate 1: substitute a problem's exact fields into its own PDE, cell model and boundary condition, symbolically."""
from __future__ import annotations

import copy
import math
from typing import Any, Mapping

from omnidriver.core.refusal import Refusal

from .problem import CURRENT, FUNCTIONS, SOURCE, SPACE, TIME, ProblemError, pde_sides, tensor_layout, validate_problem


# A mapped value is a ratio of the problem's decimals: equal to the given one up to the float's own rounding.
_SAME = 1e-12


class SymbolicUnavailable(Refusal):
    """The residual check needs sympy: install ``omnidriver-verifier[symbolic]``."""

    code = "required_check_unavailable"


def residual_verdict(problem: Mapping[str, Any]) -> dict[str, Any]:
    """Per dimension, the simplified residual of the PDE (``pde.equation``, read from the data) and of each state's
    ODE (``"0"`` when the exact fields solve them), the source the data implies beside the one it declares, the
    normal derivative of the exact unknown on each face, the exact fields at the start, and each derived constant
    beside the native literal: a dimension fails when the two differ by more than the tolerance the data states."""
    cell = problem["cell_model"]
    given = {name: problem["parameters"][name] for name in cell["parameters"] if name in problem["parameters"]}
    for name in cell["parameters"]:
        if name in problem["derived"]:
            entry = problem["derived"][name]
            given[name] = entry["native"] if entry["use"] == "native" else None
    return _verdict(problem, cell, given, {}, None)


def cell_model_verdict(
    problem: Mapping[str, Any],
    cell_model: Mapping[str, Any],
    *,
    pde_parameters: Mapping[str, float] | None = None,
    fixed_capacitance: float | None = None,
) -> dict[str, Any]:
    """Gate 1 on a generated cell model, in the shape of :func:`residual_verdict`.

    ``cell_model`` holds ``rates`` (one per state of the problem) and ``Iion``, written in the problem's names,
    and ``parameters``: the value it gives each parameter it names, a number or a per-dimension table. The PDE
    takes the problem's parameters, overridden by ``pde_parameters`` (what a solver's PDE was given). The cell
    model's own values enter its expressions, so a pair it does not share with the PDE (``shares_with_pde``)
    leaves a PDE residual; each value given either side is also reported beside the problem's, and fails when
    it differs. A derived constant is judged against its derived value within the stated tolerance.

    ``fixed_capacitance`` is the value a solver fixes the capacitance at: the PDE then takes the values the
    problem's ``units.fixed_capacitance`` maps to (unless ``pde_parameters`` says otherwise, which is then judged
    against them), the cell model's current is the solver's mapped one, and each product the mapping ``keeps``
    must be unchanged by it. :class:`ProblemError` when the cell model is malformed or gives no value to a
    parameter it names."""
    values = dict(cell_model.get("parameters", {}))
    candidate = copy.deepcopy(dict(problem))
    candidate["cell_model"].update(rates=cell_model.get("rates"), Iion=cell_model.get(CURRENT),
                                   parameters=sorted(values))
    validate_problem(candidate)
    dimensions = {str(d) for d in problem["dimensions"]}
    for name, value in values.items():
        numbers = value.values() if isinstance(value, Mapping) else [value]
        if (isinstance(value, Mapping) and set(value) != dimensions) or not all(
                isinstance(number, (int, float)) and not isinstance(number, bool) for number in numbers):
            raise ProblemError(f"cell_model.parameters.{name}: {value!r} is not a number or a per-dimension table")
    stray = sorted(set(pde_parameters or {}) - set(problem["parameters"]))
    if stray:
        raise ProblemError(f"pde_parameters: {stray} are not parameters of {problem['id']!r}")
    return _verdict(candidate, candidate["cell_model"], values, pde_parameters or {}, fixed_capacitance)


def _verdict(problem: Mapping[str, Any], cell: Mapping[str, Any], given: Mapping[str, Any],
             pde_overrides: Mapping[str, float], fixed: float | None) -> dict[str, Any]:
    sympy = _sympy()
    entries = [_dimension(sympy, problem, cell, given, pde_overrides, fixed, d) for d in problem["dimensions"]]
    return {
        "problem": problem["id"],
        "equation": problem["equation"],
        "status": "passed" if all(entry["status"] == "passed" for entry in entries) else "failed",
        "dimensions": entries,
    }


def _sympy() -> Any:
    try:
        import sympy
    except ImportError:
        raise SymbolicUnavailable(
            "the residual check needs sympy; install omnidriver-verifier[symbolic]"
        ) from None
    return sympy


def _symbol(sympy: Any, name: str, lower: float) -> Any:
    # Only the assumption the data supplies: a coordinate whose interval starts at or above zero is nonnegative.
    return sympy.Symbol(name, real=True, nonnegative=True) if lower >= 0 else sympy.Symbol(name, real=True)


def _dimension(sympy: Any, problem: Mapping[str, Any], cell: Mapping[str, Any], given: Mapping[str, Any],
               pde_overrides: Mapping[str, float], fixed: float | None, d: int) -> dict[str, Any]:
    key = str(d)

    def at(value: Any) -> Any:
        return value[key] if isinstance(value, Mapping) else value

    space = [_symbol(sympy, name, interval[0]) for name, interval in zip(SPACE[:d], problem["domain"]["box"])]
    t = _symbol(sympy, TIME, problem["time"]["start"])
    names: dict[str, Any] = {symbol.name: symbol for symbol in (*space, t)}
    names["pi"] = sympy.pi
    for function in FUNCTIONS:
        names[function] = getattr(sympy, function)
    # Exact decimals: a float coefficient would leave round-off where the residual should cancel.
    for name, value in problem["parameters"].items():
        names[name] = sympy.Rational(str(value))

    def parse(text: str, local: Mapping[str, Any] = names) -> Any:
        return sympy.parse_expr(text, local_dict=dict(local), evaluate=True)

    mapped, fixed_report = _mapped(sympy, problem, names, parse, fixed)
    pde_given = {**problem["parameters"], **mapped, **pde_overrides}
    pde_names = {**names, **{name: sympy.Rational(str(value)) for name, value in pde_given.items()}}

    derived = {}
    for name, entry in problem["derived"].items():
        names[name] = parse(entry["expression"][key])
        value = float(names[name].evalf(17))
        native = entry["native"][key]
        if name not in given:
            continue
        # A solver given the derived value itself is given it exactly.
        solver_value = value if at(given[name]) is None else at(given[name])
        difference = solver_value - value
        derived[name] = {
            "status": "passed" if abs(difference) <= entry["tolerance"] else "failed",
            "value": value, "given": solver_value, "native": native, "difference": difference,
            "tolerance": entry["tolerance"], "use": entry["use"],
        }
    for name, by_dimension in problem["fields"].items():
        names[name] = parse(by_dimension[key])
    exact = {name: parse(text) for name, text in problem["exact"].items()}

    pde = problem["pde"]
    unknown = pde["unknown"]
    # The cell model takes its own values; a derived constant keeps its exact value, judged apart above.
    own = {name: sympy.Rational(str(at(value))) for name, value in given.items() if name in problem["parameters"]}
    cell_names = {**names, **own, **{name: sympy.Symbol(f"_{name}") for name in exact}}
    substitution = {cell_names[name]: value for name, value in exact.items()}

    def on_solution(text: str) -> Any:
        return parse(text, cell_names).subs(substitution)

    operators = {
        "Derivative": lambda field, *variables: sympy.diff(field, *variables),
        "grad": lambda field: sympy.Matrix([sympy.diff(field, x) for x in space]),
        "div": lambda vector: sum(sympy.diff(vector[i], x) for i, x in enumerate(space)),
    }
    tensors = {name: sympy.Matrix([[pde_names[entry] if entry else 0 for entry in row]
                                   for row in tensor_layout(tensor, d)])
               for name, tensor in pde["tensors"].items()}
    lhs, _ = pde_sides(pde["equation"])
    implied_source = parse(lhs, {**pde_names, **operators, **tensors, unknown: exact[unknown],
                                 CURRENT: on_solution(cell[CURRENT])})
    declared_source = parse(problem["source"]["expression"])

    residuals = {"pde": _simplified(sympy, implied_source - declared_source)}
    for state in cell["states"]:
        residuals[state] = _simplified(sympy, sympy.diff(exact[state], t) - on_solution(cell["rates"][state]))
    boundary = {
        f"{x.name}={side}": _simplified(sympy, sympy.diff(exact[unknown], x).subs(x, sympy.Rational(str(side))))
        for x, sides in zip(space, problem["domain"]["box"]) for side in sides
    }
    start = sympy.Rational(str(problem["time"]["start"]))
    parameters = {}
    pde_scalars = {entry for tensor in pde["tensors"].values() for row in tensor_layout(tensor, d)
                   for entry in row if entry}
    pde_scalars |= {name for name in pde["parameters"] if name in problem["parameters"]}
    for name in sorted(pde_scalars | set(own)):
        report = {"problem": problem["parameters"][name]}
        agrees = True
        if name in pde_scalars:
            report["pde"] = pde_given[name]
            if name in mapped:
                report["mapped"] = mapped[name]
            agrees = math.isclose(report["pde"], mapped.get(name, report["problem"]), rel_tol=_SAME)
        if name in own:
            report["cell_model"] = at(given[name])
            agrees = agrees and report["cell_model"] == report["problem"]
        report["status"] = "passed" if agrees else "failed"
        parameters[name] = report
    checks = (*derived.values(), *parameters.values(), *([fixed_report] if fixed_report else []))
    passed = all(value == "0" for value in (*residuals.values(), *boundary.values())) and all(
        entry["status"] == "passed" for entry in checks)
    entry = {
        "dimension": d,
        "status": "passed" if passed else "failed",
        "residuals": residuals,
        SOURCE: {"derived": _simplified(sympy, implied_source), "declared": _simplified(sympy, declared_source)},
        "boundary": boundary,
        "initial": {name: _simplified(sympy, field.subs(t, start)) for name, field in exact.items()},
        "derived": derived,
        "parameters": parameters,
    }
    if fixed_report:
        entry["fixed_capacitance"] = fixed_report
    return entry


def _mapped(sympy: Any, problem: Mapping[str, Any], names: Mapping[str, Any], parse: Any,
            fixed: float | None) -> tuple[dict[str, float], dict[str, Any] | None]:
    """The PDE values ``units.fixed_capacitance`` maps to for a capacitance fixed at ``fixed``, and its report:
    each product it keeps, as the mapped minus the original (``"0"`` when kept)."""
    if fixed is None:
        return {}, None
    mapping = problem["units"]["fixed_capacitance"]
    current = sympy.Symbol(CURRENT)
    value = sympy.Rational(str(fixed))
    scope = {**names, mapping["value"]: value, CURRENT: current}
    after = {mapping["parameter"]: value, **{name: parse(text, scope) for name, text in mapping["maps"].items()}}
    keeps = {text: _simplified(sympy, parse(text, {**names, **after}) - parse(text, {**names, CURRENT: current}))
             for text in mapping["keeps"]}
    report = {
        mapping["value"]: fixed,
        "maps": {name: str(expression) for name, expression in after.items()},
        "keeps": keeps,
        "status": "passed" if set(keeps.values()) == {"0"} else "failed",
    }
    return {name: float(expression) for name, expression in after.items() if name != CURRENT}, report


def _simplified(sympy: Any, expression: Any) -> str:
    return str(sympy.simplify(expression))
