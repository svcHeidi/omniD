"""The shared error norm, the order fit and the cross-solver table: deterministic, and the same for every solver."""
from __future__ import annotations

import math
from typing import Any, Iterable, Mapping, Sequence

from .problem import FUNCTIONS, SPACE, TIME, ProblemError

_MATH = {name: getattr(math, name) for name in FUNCTIONS} | {"pi": math.pi}


def exact_values(problem: Mapping[str, Any], dimension: int, field: str, time: float,
                 points: Iterable[Sequence[float]]) -> list[float]:
    """The exact ``field`` of ``problem`` in ``dimension`` at ``time``, at each point (its first ``dimension``
    coordinates, in the problem's units). A derived constant takes the value its ``use`` names."""
    if dimension not in problem["dimensions"]:
        raise ProblemError(f"{problem['id']!r} has no dimension {dimension}")
    if field not in problem["exact"]:
        raise ProblemError(f"{problem['id']!r} has no exact field {field!r} ({sorted(problem['exact'])})")
    key = str(dimension)
    scope: dict[str, Any] = {**_MATH, **problem["parameters"], TIME: time}
    for name, entry in problem["derived"].items():
        scope[name] = entry["native"][key] if entry["use"] == "native" else _eval(entry["expression"][key], scope)
    fields = {name: compile(by_dimension[key], f"fields.{name}", "eval")
              for name, by_dimension in problem["fields"].items()}
    target = compile(problem["exact"][field], f"exact.{field}", "eval")
    axes = SPACE[:dimension]
    values = []
    for point in points:
        local = dict(scope, **dict(zip(axes, point)))
        for name, code in fields.items():
            local[name] = eval(code, {"__builtins__": {}}, local)
        # Every expression was validated as arithmetic over the problem's own names on load.
        values.append(eval(target, {"__builtins__": {}}, local))
    return values


def error_norms(problem: Mapping[str, Any], values: Sequence[float], exact: Sequence[float],
                weights: Sequence[float]) -> dict[str, float]:
    """Each norm of ``problem``'s ``[norms]`` of ``values - exact``: L1 and L2 weighted by ``weights`` (the cell
    volume for a finite-volume solver, the nodal control volume for a finite-element one) and normalised by their
    total, Linf the largest pointwise difference. :class:`ProblemError` for a non-finite value."""
    if not len(values) == len(exact) == len(weights) or not values:
        raise ProblemError(f"values, exact and weights must be non-empty and of one length "
                           f"({len(values)}, {len(exact)}, {len(weights)})")
    total = math.fsum(weights)
    if total <= 0 or any(weight < 0 for weight in weights):
        raise ProblemError("weights must be nonnegative with a positive total")
    for label, series in (("values", values), ("exact", exact)):
        bad = [index for index, item in enumerate(series) if not math.isfinite(item)]
        if bad:
            raise ProblemError(f"{label} hold a non-finite number at {len(bad)} points (first index {bad[0]}); "
                               f"a diverged field has no error norm", code="non_finite_values")
    errors = [abs(value - reference) for value, reference in zip(values, exact)]
    norms = {
        "L1": math.fsum(w * e for w, e in zip(weights, errors)) / total,
        "L2": math.sqrt(math.fsum(w * e * e for w, e in zip(weights, errors)) / total),
        "Linf": max(errors),
    }
    return {kind: norms[kind] for kind in problem["norms"]["kinds"]}


def observed_orders(spacings: Sequence[float], errors: Sequence[float]) -> dict[str, Any]:
    """The observed order between each pair of successive levels, ``log(e_c/e_f)/log(h_c/h_f)``, and the
    least-squares slope of ``log e`` against ``log h`` over all levels (null for a single level).
    :class:`ProblemError` for an error that is not finite and positive, or a spacing that is not finite and
    positive or repeats its predecessor."""
    if len(spacings) != len(errors):
        raise ProblemError("spacings and errors must be of one length")
    if not all(math.isfinite(h) and h > 0 for h in spacings) or any(a == b for a, b in zip(spacings, spacings[1:])):
        raise ProblemError(f"spacings must be finite, positive and successively distinct: {list(spacings)}",
                           code="spacings_unusable")
    if not all(math.isfinite(e) and e > 0 for e in errors):
        raise ProblemError(f"errors must be finite and positive to have an order: {list(errors)}",
                           code="errors_unusable")
    pairs = [math.log(ec / ef) / math.log(hc / hf)
             for (hc, ec), (hf, ef) in zip(zip(spacings, errors), zip(spacings[1:], errors[1:]))]
    slope = None
    if len(spacings) >= 2:
        xs, ys = [math.log(h) for h in spacings], [math.log(e) for e in errors]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    return {"successive": pairs, "least_squares": slope}


def comparison_table(problem: Mapping[str, Any], results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Per solver and dimension, each level's errors, evaluation time (``steps*dt``) and observed order against
    the previous level, the least-squares order over the levels, and the solver's stated orders as it gave them.

    Each result is ``{"solver", "problem", "mesh", "stated", "levels": [{"dimension", "cells_per_axis", "dt",
    "steps", "errors": {field: {kind: value}}}]}``. :class:`ProblemError` for a result of another problem, a mesh
    kind or level off the problem's ladder, or a norm the problem does not name."""
    fields, kinds = problem["norms"]["fields"], problem["norms"]["kinds"]
    rows = []
    for result in results:
        _require("a result", result, ("solver", "problem", "mesh", "levels"))
        solver = result["solver"]
        if result["problem"] != problem["id"]:
            raise ProblemError(f"{solver}: a result of {result['problem']!r}, not {problem['id']!r}")
        ladder = problem["refinement"].get(result["mesh"])
        if ladder is None:
            raise ProblemError(f"{solver}: mesh {result['mesh']!r} is not in {sorted(problem['refinement'])}")
        rungs = {cells: (dt, steps) for cells, dt, steps in zip(ladder["cells_per_axis"], ladder["dt"], ladder["steps"])}
        by_dimension: dict[int, list[Mapping[str, Any]]] = {}
        for level in result["levels"]:
            _require(f"{solver}: a level", level, ("dimension", "cells_per_axis", "dt", "steps", "errors"))
            cells, d = level["cells_per_axis"], level["dimension"]
            if d not in problem["dimensions"] or rungs.get(cells) != (level["dt"], level["steps"]):
                raise ProblemError(f"{solver}: level {d}D N={cells} dt={level['dt']} steps={level['steps']} is off "
                                   f"the problem's {result['mesh']} ladder")
            missing = [f"{field}.{kind}" for field in fields if field in level["errors"]
                       for kind in kinds if kind not in level["errors"][field]]
            stray = sorted(set(level["errors"]) - set(fields))
            if missing or stray or not level["errors"]:
                raise ProblemError(f"{solver}: level {d}D N={cells} misses {missing} or names fields {stray} "
                                   f"outside norms.fields {fields}")
            by_dimension.setdefault(d, []).append(level)
        for d, levels in sorted(by_dimension.items()):
            levels = sorted(levels, key=lambda level: level["cells_per_axis"])
            edge = problem["domain"]["box"][0][1] - problem["domain"]["box"][0][0]
            spacings = [edge / level["cells_per_axis"] for level in levels]
            orders = {field: {kind: observed_orders(spacings, [level["errors"][field][kind] for level in levels])
                              for kind in kinds}
                      for field in fields if all(field in level["errors"] for level in levels)}
            rows.append({
                "solver": solver, "dimension": d, "mesh": result["mesh"], "stated": result.get("stated"),
                "levels": [
                    {"cells_per_axis": level["cells_per_axis"], "h": h, "dt": level["dt"], "steps": level["steps"],
                     "time": level["steps"] * level["dt"], "errors": level["errors"],
                     "observed_order": {field: {kind: (orders[field][kind]["successive"][index - 1] if index else None)
                                                for kind in kinds} for field in orders}}
                    for index, (level, h) in enumerate(zip(levels, spacings))
                ],
                "least_squares_order": {field: {kind: orders[field][kind]["least_squares"] for kind in kinds}
                                        for field in orders},
            })
    return {"status": "ok", "problem": problem["id"], "rows": rows}


def _require(where: str, item: Any, keys: tuple[str, ...]) -> None:
    missing = [key for key in keys if not isinstance(item, Mapping) or key not in item]
    if missing:
        raise ProblemError(f"{where} misses {missing}", code="results_invalid")


def _eval(text: str, scope: Mapping[str, Any]) -> float:
    return eval(compile(text, "derived", "eval"), {"__builtins__": {}}, dict(scope))
