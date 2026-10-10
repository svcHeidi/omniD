"""Gate 1: substitute a problem's exact fields into its own PDE, cell model and boundary condition, symbolically."""
from __future__ import annotations

from typing import Any, Mapping

from omnidriver.core.refusal import Refusal

from .problem import CURRENT, FUNCTIONS, SOURCE, SPACE, TIME, pde_sides


class SymbolicUnavailable(Refusal):
    """The residual check needs sympy: install ``omnidriver-verifier[symbolic]``."""

    code = "required_check_unavailable"


def residual_verdict(problem: Mapping[str, Any]) -> dict[str, Any]:
    """Per dimension, the simplified residual of the PDE (``pde.equation``, read from the data) and of each state's
    ODE (``"0"`` when the exact fields solve them), the source the data implies beside the one it declares, the
    normal derivative of the exact unknown on each face, the exact fields at the start, and each derived constant
    beside the native literal: a dimension fails when the two differ by more than the tolerance the data states."""
    sympy = _sympy()
    entries = [_dimension(sympy, problem, d) for d in problem["dimensions"]]
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


def _dimension(sympy: Any, problem: Mapping[str, Any], d: int) -> dict[str, Any]:
    key = str(d)
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

    derived = {}
    for name, entry in problem["derived"].items():
        names[name] = parse(entry["expression"][key])
        value = float(names[name].evalf(17))
        native = entry["native"][key]
        difference = native - value
        derived[name] = {
            "status": "passed" if abs(difference) <= entry["tolerance"] else "failed",
            "value": value, "native": native, "difference": difference, "tolerance": entry["tolerance"],
            "use": entry["use"],
        }
    for name, by_dimension in problem["fields"].items():
        names[name] = parse(by_dimension[key])
    exact = {name: parse(text) for name, text in problem["exact"].items()}

    pde = problem["pde"]
    cell = problem["cell_model"]
    unknown = pde["unknown"]
    cell_names = {**names, **{name: sympy.Symbol(f"_{name}") for name in exact}}
    substitution = {cell_names[name]: value for name, value in exact.items()}

    def on_solution(text: str) -> Any:
        return parse(text, cell_names).subs(substitution)

    operators = {
        "Derivative": lambda field, *variables: sympy.diff(field, *variables),
        "grad": lambda field: sympy.Matrix([sympy.diff(field, x) for x in space]),
        "div": lambda vector: sum(sympy.diff(vector[i], x) for i, x in enumerate(space)),
    }
    tensors = {name: sympy.diag(*(names[entry] for entry in tensor["diagonal"][:d]))
               for name, tensor in pde["tensors"].items()}
    lhs, _ = pde_sides(pde["equation"])
    implied_source = parse(lhs, {**names, **operators, **tensors, unknown: exact[unknown],
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
    passed = all(value == "0" for value in (*residuals.values(), *boundary.values())) and all(
        entry["status"] == "passed" for entry in derived.values())
    return {
        "dimension": d,
        "status": "passed" if passed else "failed",
        "residuals": residuals,
        SOURCE: {"derived": _simplified(sympy, implied_source), "declared": _simplified(sympy, declared_source)},
        "boundary": boundary,
        "initial": {name: _simplified(sympy, field.subs(t, start)) for name, field in exact.items()},
        "derived": derived,
    }


def _simplified(sympy: Any, expression: Any) -> str:
    return str(sympy.simplify(expression))
