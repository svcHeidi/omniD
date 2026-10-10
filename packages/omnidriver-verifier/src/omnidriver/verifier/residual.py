"""Gate 1: substitute a problem's exact fields into its equation, cell model and boundary condition, symbolically."""
from __future__ import annotations

from typing import Any, Mapping

from omnidriver.core.refusal import Refusal

from .problem import POTENTIAL, SPACE, TIME


class SymbolicUnavailable(Refusal):
    """The residual check needs sympy: install ``omnidriver-verifier[symbolic]``."""

    code = "required_check_unavailable"


def residual_verdict(problem: Mapping[str, Any]) -> dict[str, Any]:
    """Per dimension, the simplified residual of the equation and of each state's ODE (``"0"`` when the exact
    fields solve them), the source the data implies beside the one it declares, the normal derivative of the exact
    potential on each face, and each derived constant beside the native literal: a dimension fails when the two
    differ by more than the tolerance the data states."""
    try:
        import sympy
    except ImportError:
        raise SymbolicUnavailable(
            "the residual check needs sympy; install omnidriver-verifier[symbolic]"
        ) from None
    entries = [_dimension(sympy, problem, d) for d in problem["dimensions"]]
    return {
        "problem": problem["id"],
        "equation": problem["equation"],
        "status": "passed" if all(entry["status"] == "passed" for entry in entries) else "failed",
        "dimensions": entries,
    }


def _dimension(sympy: Any, problem: Mapping[str, Any], d: int) -> dict[str, Any]:
    key = str(d)
    space = [sympy.Symbol(name, real=True, nonnegative=True) for name in SPACE[:d]]
    t = sympy.Symbol(TIME, real=True, nonnegative=True)
    names: dict[str, Any] = {symbol.name: symbol for symbol in (*space, t)}
    names["pi"] = sympy.pi
    for function in ("sqrt", "cos", "sin", "exp", "log"):
        names[function] = getattr(sympy, function)
    # Exact decimals: a float coefficient would leave round-off where the residual should cancel.
    for name, value in problem["parameters"].items():
        names[name] = sympy.Rational(str(value))

    def parse(text: str) -> Any:
        return sympy.parse_expr(text, local_dict=names, evaluate=True)

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

    cell = problem["cell_model"]
    unknowns = {POTENTIAL: exact[POTENTIAL], **{state: exact[state] for state in cell["states"]}}
    cell_names = {**names, **{name: sympy.Symbol(f"_{name}") for name in unknowns}}
    substitution = {cell_names[name]: value for name, value in unknowns.items()}

    def on_solution(text: str) -> Any:
        return sympy.parse_expr(text, local_dict=cell_names, evaluate=True).subs(substitution)

    potential = exact[POTENTIAL]
    sigma = [names[f"sigma_{axis}{axis}"] for axis in SPACE[:d]]
    diffusion = sum(s * sympy.diff(potential, x, 2) for s, x in zip(sigma, space))
    implied_source = names["chi"] * (names["Cm"] * sympy.diff(potential, t) + on_solution(cell["Iion"])) - diffusion
    declared_source = parse(problem["source"]["expression"])

    residuals = {"pde": _simplified(sympy, implied_source - declared_source)}
    for state in cell["states"]:
        residuals[state] = _simplified(sympy, sympy.diff(exact[state], t) - on_solution(cell["rates"][state]))
    boundary = {
        f"{x.name}={side}": _simplified(sympy, sympy.diff(potential, x).subs(x, sympy.Rational(str(side))))
        for x, sides in zip(space, problem["domain"]["box"]) for side in sides
    }
    passed = all(value == "0" for value in (*residuals.values(), *boundary.values())) and all(
        entry["status"] == "passed" for entry in derived.values())
    return {
        "dimension": d,
        "status": "passed" if passed else "failed",
        "residuals": residuals,
        "source": {"derived": _simplified(sympy, implied_source), "declared": _simplified(sympy, declared_source)},
        "boundary": boundary,
        "derived": derived,
    }


def _simplified(sympy: Any, expression: Any) -> str:
    return str(sympy.simplify(expression))
