"""The bounds +Help gives a parameter, judged over a resolved case's ``.par`` values.

A bound is a number, a parameter, or arithmetic over them (``dt/1000.``, ``tend-stim[PrMelem1].ptcl.start``);
one the grammar below cannot evaluate is reported as a note, not judged."""
from __future__ import annotations

import ast
import operator
import re
from pathlib import Path

from omnidriver.core.planning_types import StrictDiagnostic, diagnostic

from .catalog import load_catalog, number_of, template_name
from .par_format import ParFormatError, parse_par, unquote
from .records import TUTORIAL_RECORDS
from .validation import read_documents

#: A parameter as +Help writes it in a bound: dotted names, each with an optional index (``stim[PrMelem1].ptcl.start``).
_REFERENCE = re.compile(r"(?<![\w.])[A-Za-z_]\w*(?:\[\w+\])?(?:\.[A-Za-z_]\w*(?:\[\w+\])?)*")
_PARENT_INDEX = re.compile(r"\[PrMelem(\d+)\]")
_OPERATORS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


class _Unevaluable(Exception):
    pass


def _evaluate(expression: str, key: str, value_of) -> float:
    """``expression`` at the values of its parameters, ``[PrMelemN]`` standing for the Nth index of ``key``.
    Only numbers, parameters, ``+ - * /`` and unary signs are evaluated; anything else raises ``_Unevaluable``."""
    indexes = re.findall(r"\[(\d+)\]", key)
    expression = _PARENT_INDEX.sub(
        lambda m: f"[{indexes[int(m[1]) - 1]}]" if 0 < int(m[1]) <= len(indexes) else m[0], expression,
    )
    parameters: dict[str, str] = {}

    def placeholder(match: re.Match[str]) -> str:
        parameters[f"p{len(parameters)}"] = match[0]
        return f"p{len(parameters) - 1}"

    try:
        tree = ast.parse(_REFERENCE.sub(placeholder, expression), mode="eval")
    except SyntaxError:
        raise _Unevaluable from None

    def walk(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return float(node.value)
        if isinstance(node, ast.Name) and node.id in parameters:
            value = value_of(parameters[node.id])
            if value is None:
                raise _Unevaluable
            return value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
            try:
                return _OPERATORS[type(node.op)](walk(node.left), walk(node.right))
            except ZeroDivisionError:
                raise _Unevaluable from None
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            return -walk(node.operand) if isinstance(node.op, ast.USub) else walk(node.operand)
        raise _Unevaluable

    return walk(tree)


def case_diagnostics(case_root: Path) -> tuple[StrictDiagnostic, ...]:
    """An error for a value beyond a bound, evaluated at the case's values (a record's command-line value,
    else the document's, else the catalogue's default) of the parameters it names; a note for each bound
    it cannot evaluate."""
    catalog = load_catalog()
    found: list[StrictDiagnostic] = []
    for document, command_line in read_documents(TUTORIAL_RECORDS).items():
        path = Path(case_root) / document
        if not path.is_file():
            continue
        try:
            assignments = parse_par(path.read_text())
        except (OSError, ParFormatError) as exc:
            found.append(diagnostic("error", "case_unreadable", f"{path} cannot be read: {exc}", source=document))
            continue
        set_here = {a.key: unquote(a.value) for a in assignments if a.value is not None}
        resolved = {**set_here, **{key: owner.value for key, owner in command_line.items()}}

        def value_of(name: str) -> float | None:
            spec = catalog.parameters.get(template_name(name))
            return number_of(resolved.get(name, spec.default if spec is not None else None))

        for key, raw in set_here.items():
            spec = catalog.parameters.get(template_name(key))
            value = number_of(raw)
            if spec is None or spec.value_kind not in ("integer", "scalar") or value is None:
                continue
            for bound, label, beyond in (
                (spec.minimum, "minimum", operator.lt), (spec.maximum, "maximum", operator.gt),
            ):
                if bound is None:
                    continue
                try:
                    limit = _evaluate(bound, key, value_of)
                except _Unevaluable:
                    found.append(diagnostic(
                        "info", "opencarp_bound_not_checked",
                        f"{key}: its {label} is {bound!r}, which omniD cannot evaluate against the case; "
                        "the bound was not checked",
                        source=document, field=key,
                    ))
                    continue
                if beyond(value, limit):
                    found.append(diagnostic(
                        "error", "catalog_rule",
                        f"{key} = {raw} is beyond its {label}, {bound} = {limit:g}",
                        source=document, field=key,
                    ))
    return tuple(found)
