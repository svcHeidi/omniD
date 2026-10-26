"""The shared error norm, the order fit and the cross-solver table: deterministic, and the same for every solver."""
from __future__ import annotations

import math
from typing import Any, Iterable, Mapping, Sequence

from .problem import FUNCTIONS, SPACE, TEMPORAL, TIME, ProblemError
from .weights import cell_volume_weights, nodal_control_volumes, tetrahedron_nodal_volumes

#: The decimals an order is given to, for every reference.
_DIGITS = 3

_MATH = {name: getattr(math, name) for name in FUNCTIONS} | {"pi": math.pi}


def exact_values(problem: Mapping[str, Any], dimension: int, field: str, time: float,
                 points: Iterable[Sequence[float]]) -> list[float]:
    """The exact ``field`` of ``problem`` in ``dimension`` at ``time``, at each point (its first ``dimension``
    coordinates, in the problem's units). A derived constant takes the value its ``use`` names."""
    if dimension not in problem["dimensions"]:
        raise ProblemError(f"{problem['id']!r} has no dimension {dimension}")
    if field not in problem["exact"]:
        raise ProblemError(f"{problem['id']!r} has no exact field {field!r} ({sorted(problem['exact'])})")
    return _evaluate(problem, dimension, problem["exact"][field], time, points)


def source_values(problem: Mapping[str, Any], dimension: int, time: float,
                  points: Iterable[Sequence[float]]) -> list[float]:
    """The problem's ``source`` (the right-hand side of its PDE) in ``dimension`` at ``time``, at each point, for a
    solver that must be given it."""
    if dimension not in problem["dimensions"]:
        raise ProblemError(f"{problem['id']!r} has no dimension {dimension}")
    return _evaluate(problem, dimension, problem["source"]["expression"], time, points)


def _evaluate(problem: Mapping[str, Any], dimension: int, expression: str, time: float,
              points: Iterable[Sequence[float]]) -> list[float]:
    key = str(dimension)
    scope: dict[str, Any] = {**_MATH, **problem["parameters"], TIME: time}
    for name, entry in problem["derived"].items():
        scope[name] = entry["native"][key] if entry["use"] == "native" else _eval(entry["expression"][key], scope)
    target = compile(expression, "expression", "eval")
    # A field the expression does not name is not evaluated: a source field can cost far more than the unknown's.
    fields = {name: compile(by_dimension[key], f"fields.{name}", "eval")
              for name, by_dimension in problem["fields"].items() if name in target.co_names}
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


def norms_verdict(problem: Mapping[str, Any], spec: Mapping[str, Any]) -> dict[str, Any]:
    """A solver's field against the problem's exact one, as the problem's error norms.

    ``spec`` is ``{"dimension", "field", "time", "points", "values", "weights"}``: ``points`` and ``values`` are the
    solver's, point by point, in the problem's units. ``weights`` is a list of one weight per point, or the
    problem's weight named by ``"weight"``: ``{"weight": "cell_volume", "cells_per_axis", "edge"}`` (a uniform grid
    of ``dimension``) or ``{"weight": "nodal_control_volume", "elements", "element"}`` (a finite-element mesh on
    ``points``; ``element`` is ``"structured"`` for lines, quadrilaterals and hexahedra, or ``"tetrahedron"``).
    :class:`ProblemError` for a missing key, a weight the problem's ``norms.weight`` does not offer, or a weight
    count that is not the point count."""
    _require("the norms input", spec, ("dimension", "field", "time", "points", "values", "weights"))
    weights = spec["weights"]
    if isinstance(weights, Mapping):
        weights = _named_weights(problem, spec, weights)
    exact = exact_values(problem, spec["dimension"], spec["field"], spec["time"], spec["points"])
    return {
        "status": "ok", "problem": problem["id"], "dimension": spec["dimension"], "field": spec["field"],
        "time": spec["time"], "points": len(spec["points"]),
        "norms": error_norms(problem, spec["values"], exact, weights),
    }


def _named_weights(problem: Mapping[str, Any], spec: Mapping[str, Any], named: Mapping[str, Any]) -> list[float]:
    _require("the weights", named, ("weight",))
    kind, offered = named["weight"], sorted(problem["norms"]["weight"].values())
    if kind not in offered:
        raise ProblemError(f"the weights: {kind!r} is not one of {offered}", code="results_invalid")
    if kind == "cell_volume":
        _require("the weights", named, ("cells_per_axis", "edge"))
        return cell_volume_weights(named["cells_per_axis"], spec["dimension"], named["edge"])
    _require("the weights", named, ("elements", "element"))
    if named["element"] not in ("structured", "tetrahedron"):
        raise ProblemError(f"the weights: element {named['element']!r} is not 'structured' or 'tetrahedron'",
                           code="results_invalid")
    build = tetrahedron_nodal_volumes if named["element"] == "tetrahedron" else nodal_control_volumes
    return build(spec["points"], named["elements"])


def observed_orders(spacings: Sequence[float], errors: Sequence[float]) -> dict[str, Any]:
    """The observed order between each pair of successive levels, ``log(e_c/e_f)/log(h_c/h_f)``, and the
    least-squares slope of ``log e`` against ``log h`` over all levels (null for a single level).
    Orders are rounded to 0.001, as :func:`orders_against_a_finer_level`'s are. :class:`ProblemError` for an
    error that is not finite and positive, or a spacing that is not finite and positive or repeats its
    predecessor."""
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
    return {"successive": [round(p, _DIGITS) for p in pairs], "least_squares": round(slope, _DIGITS)
            if slope is not None else None}


#: The orders a fit against a finer level's solution can find: an error ratio outside what these orders give
#: has no order.
_ORDER_RANGE = (0.05, 8.0)


def orders_against_a_finer_level(spacings: Sequence[float], errors: Sequence[float],
                                 reference: float) -> dict[str, Any]:
    """The observed order of errors measured against the solution at a finer ``reference`` spacing rather than the
    exact one: for an order ``p``, the error at ``h`` is ``C*(h**p - reference**p)``, so the plain log-ratio of
    successive errors is biased toward a higher order. Each successive order solves
    ``(h_c**p - r**p)/(h_f**p - r**p) = e_c/e_f`` for ``p``; the least-squares order minimises the squared residual
    of ``log e`` against ``log C + log(h**p - r**p)`` over all levels (both to 0.001, null for fewer than two levels,
    and an order outside 0.05 to 8 is null). :class:`ProblemError` as for :func:`observed_orders`, for spacings
    that are not strictly decreasing, and for a spacing not above ``reference``."""
    observed_orders(spacings, errors)
    if any(a < b for a, b in zip(spacings, spacings[1:])):
        raise ProblemError(f"spacings must decrease from the coarsest level: {list(spacings)}",
                           code="spacings_unusable")
    if not all(h > reference for h in spacings) or not reference > 0:
        raise ProblemError(f"spacings {list(spacings)} must all exceed the reference {reference} > 0",
                           code="spacings_unusable")
    shape = lambda h, p: math.log(h**p - reference**p)
    low, high = _ORDER_RANGE

    def successive(hc: float, hf: float, ratio: float) -> float | None:
        gap = lambda p: shape(hc, p) - shape(hf, p) - math.log(ratio)
        if gap(low) > 0 or gap(high) < 0:
            return None
        a, b = low, high
        while b - a > 1e-4:
            mid = (a + b) / 2
            a, b = (mid, b) if gap(mid) < 0 else (a, mid)
        return round((a + b) / 2, _DIGITS)

    pairs = [successive(hc, hf, ec / ef)
             for (hc, ec), (hf, ef) in zip(zip(spacings, errors), zip(spacings[1:], errors[1:]))]
    slope = None
    if len(spacings) >= 2:
        ys = [math.log(e) for e in errors]

        def residual(p: float) -> float:
            xs = [shape(h, p) for h in spacings]
            offset = sum(y - x for x, y in zip(xs, ys)) / len(xs)
            return sum((y - x - offset) ** 2 for x, y in zip(xs, ys))

        grid = [low + k * 0.001 for k in range(int((high - low) / 0.001) + 1)]
        best = min(grid, key=residual)
        slope = None if best in (grid[0], grid[-1]) else round(best, _DIGITS)
    return {"successive": pairs, "least_squares": slope}


def comparison_table(problem: Mapping[str, Any], results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Per solver and dimension, each level's errors, evaluation time (``steps*dt``) and observed order against
    the previous level, the least-squares order over the levels, and the solver's stated orders as it gave them.
    Orders are fitted against the box edge over N (the ladder's label) unless every level of a dimension carries a
    ``mesh_size`` (a mesh-measured length such as the mean edge, in the problem's units), which is then used and
    named in the row's ``spacing``.

    Each result is ``{"solver", "problem", "mesh", "stated", "levels": [{"dimension", "cells_per_axis", "dt",
    "steps", "errors": {field: {kind: value}}}]}``. :class:`ProblemError` for a result of another problem, a mesh
    kind or level off the problem's ladder, a level listed twice, a field given at only some of a dimension's levels, or a norm the problem does not name."""
    fields, kinds = problem["norms"]["fields"], problem["norms"]["kinds"]
    rows = []
    for result in results:
        _require("a result", result, ("solver", "problem", "mesh", "levels"))
        solver = result["solver"]
        if result["problem"] != problem["id"]:
            raise ProblemError(f"{solver}: a result of {result['problem']!r}, not {problem['id']!r}")
        if result["mesh"] not in problem["mesh_progression"]:
            raise ProblemError(f"{solver}: mesh {result['mesh']!r} is not in {problem['mesh_progression']}")
        ladder = problem["refinement"][result["mesh"]]
        rungs = {cells: (dt, steps) for cells, dt, steps in zip(ladder["cells_per_axis"], ladder["dt"], ladder["steps"])}
        by_dimension: dict[int, list[Mapping[str, Any]]] = {}
        for level in result["levels"]:
            _require(f"{solver}: a level", level, ("dimension", "cells_per_axis", "dt", "steps", "errors"))
            cells, d = level["cells_per_axis"], level["dimension"]
            if d not in ladder["dimensions"] or rungs.get(cells) != (level["dt"], level["steps"]):
                raise ProblemError(f"{solver}: level {d}D N={cells} dt={level['dt']} steps={level['steps']} is off "
                                   f"the problem's {result['mesh']} ladder")
            missing = [f"{field}.{kind}" for field in fields if field in level["errors"]
                       for kind in kinds if kind not in level["errors"][field]]
            stray = sorted(set(level["errors"]) - set(fields))
            if missing or stray or not level["errors"]:
                raise ProblemError(f"{solver}: level {d}D N={cells} misses {missing} or names fields {stray} "
                                   f"outside norms.fields {fields}")
            if any(other["cells_per_axis"] == cells for other in by_dimension.get(d, [])):
                raise ProblemError(f"{solver}: level {d}D N={cells} is listed twice", code="results_invalid")
            by_dimension.setdefault(d, []).append(level)
        for d, levels in sorted(by_dimension.items()):
            levels = sorted(levels, key=lambda level: level["cells_per_axis"])
            partial = [field for field in fields if 0 < sum(field in level["errors"] for level in levels) < len(levels)]
            if partial:
                raise ProblemError(f"{solver}: {d}D field(s) {partial} are given at only some of the levels",
                                   code="results_invalid")
            edge = problem["domain"]["box"][0][1] - problem["domain"]["box"][0][0]
            measured = [level.get("mesh_size") for level in levels]
            if any(size is not None for size in measured) and any(size is None for size in measured):
                raise ProblemError(f"{solver}: {d}D mesh_size is given at only some of the levels",
                                   code="results_invalid")
            spacings = [edge / level["cells_per_axis"] for level in levels] if measured[0] is None else measured
            orders = {field: {kind: observed_orders(spacings, [level["errors"][field][kind] for level in levels])
                              for kind in kinds}
                      for field in fields if field in levels[0]["errors"]}
            rows.append({
                "solver": solver, "dimension": d, "mesh": result["mesh"], "stated": result.get("stated"),
                "spacing": "edge_over_n" if measured[0] is None else "mesh_size",
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


#: What a temporal level's errors are measured against: the exact solution; the same solver's finest-dt solution
#: on the same mesh, each level's own exact error less the finest level's, point by point, which removes the spatial
#: error both share and the difference between their evaluation times; or the same solver's dt -> 0 limit on the
#: same mesh (its error fields extrapolated in dt, each level's exact error less the limit's), which removes the
#: spatial error and leaves every level, the finest included, with its own temporal error.
TEMPORAL_REFERENCES = ("exact", "finest_dt", "extrapolated")

#: A configuration converges to the exact solution only if its least-squares order against it reaches this and its
#: error at the finest dt is below the coarsest's.
MIN_CONVERGING_ORDER = 0.5

#: A successive order this far from the one before it marks the finest level floor-contaminated.
FLOOR_JUMP = 0.25


def floor_contaminated(errors: Sequence[float], orders: Sequence[float | None]) -> bool:
    """Whether the finest level of a coarse-to-fine error sequence sits on a floor (the spatial or round-off error
    the ladder does not refine) instead of the trend: its error did not decrease, or its successive order differs
    by more than :data:`FLOOR_JUMP` from the one before it (a drift smaller than that per level is a trend, not a
    floor). ``orders`` are the successive orders, one fewer than ``errors``; with fewer than two there is no trend
    to depart from."""
    if len(errors) >= 2 and errors[-1] >= errors[-2]:
        return True
    return len(orders) >= 2 and abs(orders[-1] - orders[-2]) > FLOOR_JUMP


def temporal_table(problem: Mapping[str, Any], results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Per solver, configuration, reference and dimension of the problem's temporal ladder, each level's errors,
    evaluation time (``steps*dt``) and observed order in ``dt`` against the previous level, the least-squares order
    over the levels, and the stated orders as the result gives them. Against the finest dt the orders are
    :func:`orders_against_a_finer_level`'s, and the row records that ``reference_dt``.

    Every row names whether the spatial error is out of its errors (``spatial_floor_removed``: false for ``exact``,
    true for ``finest_dt`` and ``extrapolated``). Every ``exact`` and ``extrapolated`` row says whether its finest
    level is :func:`floor_contaminated` per field and norm (``floor_contaminated``), and the least-squares order
    without that level where it is (``least_squares_order_without_floor``, else null); a contaminated order is not
    the scheme's. A configuration ``converges`` to its reference only if every norm's least-squares order reaches
    :data:`MIN_CONVERGING_ORDER` and its finest-dt error is below its coarsest. A ``finest_dt`` row carries the
    verdict of the ``extrapolated`` row of its solver, configuration, dimension and mesh, else of the ``exact`` one,
    as ``converges_to_reference`` (null when neither is given) and names which as ``verdict_from``, because an order
    against a solution the scheme does not converge to is the order of its dt-dependent part only, never a verdict
    by itself. An ``extrapolated`` result may carry ``extrapolation``, how its limit was obtained, which its row
    repeats.

    The ladder's mesh is ``cells_per_axis``; a ``finer_cells_per_axis`` the problem declares is a second mesh of
    the same dt ladder, which lowers the spatial error, and its levels make rows of their own.

    Each result is ``{"solver", "problem", "configuration", "reference", "stated", "levels": [{"dimension",
    "cells_per_axis", "dt", "steps", "errors": {field: {kind: value}}}]}``, ``reference`` one of
    :data:`TEMPORAL_REFERENCES`. :class:`ProblemError` for a problem with no temporal ladder, a level off it (a
    ``finest_dt`` result's finest level among them, whose error is zero by construction), a level listed twice, a
    norm missing, a field given at only some of a dimension's levels, or a ``reference_dt`` the result declares
    that is not the ladder's finest dt for ``finest_dt`` (or is declared for ``exact``)."""
    ladder = problem["refinement"].get(TEMPORAL)
    if ladder is None:
        raise ProblemError(f"{problem['id']!r} has no refinement.{TEMPORAL}")
    fields, kinds = problem["norms"]["fields"], problem["norms"]["kinds"]
    rungs = dict(zip(ladder["dt"], ladder["steps"]))
    finer = ladder.get("finer_cells_per_axis", {})
    meshes = {int(d): {n, *([finer[d]] if d in finer else [])} for d, n in ladder["cells_per_axis"].items()}
    finest = min(ladder["dt"])
    rows = []
    for result in results:
        _require("a result", result, ("solver", "problem", "configuration", "reference", "levels"))
        solver, reference = result["solver"], result["reference"]
        label = f"{solver} {result['configuration']}"
        if result["problem"] != problem["id"]:
            raise ProblemError(f"{label}: a result of {result['problem']!r}, not {problem['id']!r}")
        if reference not in TEMPORAL_REFERENCES:
            raise ProblemError(f"{label}: reference {reference!r} is not one of {list(TEMPORAL_REFERENCES)}",
                               code="results_invalid")
        if "reference_dt" in result and result["reference_dt"] != (finest if reference == "finest_dt" else None):
            raise ProblemError(f"{label}: reference_dt {result['reference_dt']!r} does not match reference "
                               f"{reference!r} (the finest dt of the ladder is {finest})", code="results_invalid")
        by_dimension: dict[tuple[int, int], list[Mapping[str, Any]]] = {}
        for level in result["levels"]:
            _require(f"{label}: a level", level, ("dimension", "cells_per_axis", "dt", "steps", "errors"))
            d, dt = level["dimension"], level["dt"]
            on_ladder = (d in ladder["dimensions"] and level["cells_per_axis"] in meshes[d]
                         and rungs.get(dt) == level["steps"])
            if not on_ladder or (reference == "finest_dt" and dt == finest):
                raise ProblemError(f"{label}: level {d}D N={level['cells_per_axis']} dt={dt} steps={level['steps']} "
                                   f"is off the problem's {TEMPORAL} ladder for reference {reference!r}",
                                   code="results_invalid")
            key = (d, level["cells_per_axis"])
            if any(other["dt"] == dt for other in by_dimension.get(key, [])):
                raise ProblemError(f"{label}: level {d}D N={key[1]} dt={dt} is listed twice", code="results_invalid")
            given = level["errors"]
            missing = [f"{field}.{kind}" for field in given for kind in kinds if kind not in given[field]]
            if not given or missing or not set(given) <= set(fields):
                raise ProblemError(f"{label}: level {d}D dt={dt} misses {missing} or names fields outside "
                                   f"norms.fields {fields}", code="results_invalid")
            by_dimension.setdefault(key, []).append(level)
        for (d, n), levels in sorted(by_dimension.items()):
            levels = sorted(levels, key=lambda level: -level["dt"])
            named = [field for field in fields if field in levels[0]["errors"]]
            if any(set(level["errors"]) != set(named) for level in levels):
                raise ProblemError(f"{label}: {d}D levels name different fields", code="results_invalid")
            dts = [level["dt"] for level in levels]
            fit = (lambda h, e: orders_against_a_finer_level(h, e, finest)) if reference == "finest_dt" else observed_orders
            orders = {field: {kind: fit(dts, [level["errors"][field][kind] for level in levels])
                              for kind in kinds} for field in named}
            series = {field: {kind: [level["errors"][field][kind] for level in levels] for kind in kinds}
                      for field in named}
            row = {
                "solver": solver, "configuration": result["configuration"], "reference": reference,
                "reference_dt": finest if reference == "finest_dt" else None,
                "dimension": d, "cells_per_axis": n, "stated": result.get("stated"),
                "spatial_floor_removed": reference != "exact",
                "levels": [
                    {"dt": level["dt"], "steps": level["steps"], "time": level["steps"] * level["dt"],
                     "errors": {field: level["errors"][field] for field in named},
                     "observed_order": {field: {kind: (orders[field][kind]["successive"][index - 1] if index else None)
                                                for kind in kinds} for field in named}}
                    for index, level in enumerate(levels)
                ],
                "least_squares_order": {field: {kind: orders[field][kind]["least_squares"] for kind in kinds}
                                        for field in named},
            }
            if reference == "extrapolated":
                row["extrapolation"] = result.get("extrapolation")
            if reference != "finest_dt":
                flags = {field: {kind: floor_contaminated(series[field][kind], orders[field][kind]["successive"])
                                 for kind in kinds} for field in named}
                row["floor_contaminated"] = flags
                row["least_squares_order_without_floor"] = {
                    field: {kind: (observed_orders(dts[:-1], series[field][kind][:-1])["least_squares"]
                                   if flags[field][kind] and len(dts) > 2 else None) for kind in kinds}
                    for field in named}
                row["converges"] = all(
                    orders[field][kind]["least_squares"] is not None
                    and orders[field][kind]["least_squares"] >= MIN_CONVERGING_ORDER
                    and series[field][kind][-1] < series[field][kind][0]
                    for field in named for kind in kinds)
            rows.append(row)
    verdicts: dict[tuple, tuple[str, bool]] = {}
    for kind in ("exact", "extrapolated"):
        for row in rows:
            if row["reference"] == kind:
                verdicts[(row["solver"], row["configuration"], row["dimension"], row["cells_per_axis"])] = (
                    kind, row["converges"])
    for row in rows:
        if row["reference"] == "finest_dt":
            row["verdict_from"], row["converges_to_reference"] = verdicts.get(
                (row["solver"], row["configuration"], row["dimension"], row["cells_per_axis"]), (None, None))
    return {"status": "ok", "problem": problem["id"], "refinement": TEMPORAL, "rows": rows}


def _require(where: str, item: Any, keys: tuple[str, ...]) -> None:
    missing = [key for key in keys if not isinstance(item, Mapping) or key not in item]
    if missing:
        raise ProblemError(f"{where} misses {missing}", code="results_invalid")


def _eval(text: str, scope: Mapping[str, Any]) -> float:
    return eval(compile(text, "derived", "eval"), {"__builtins__": {}}, dict(scope))
