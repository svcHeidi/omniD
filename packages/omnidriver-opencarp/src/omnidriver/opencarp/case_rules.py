"""The bounds +Help gives a parameter as a parameter's name, judged over a resolved case's ``.par`` values.

A bound written as a number is checked when a study sets the key (``validation``); one written as an expression (``dt/1000.``) is not evaluated, and says so."""
from __future__ import annotations

import re
from pathlib import Path

from omnidriver.core.planning_types import StrictDiagnostic, diagnostic

from .catalog import load_catalog, template_name
from .par_format import ParFormatError, parse_par, unquote
from .records import TUTORIAL_RECORDS
from .validation import _LITERAL_NUMBER, read_documents

_PARAMETER_NAME = re.compile(r"[A-Za-z_]\w*")


def case_diagnostics(case_root: Path) -> tuple[StrictDiagnostic, ...]:
    """An error for a value beyond a bound that names another parameter, evaluated at that parameter's
    value in the case (a record's command-line value, else the document's, else the catalogue's default);
    a warning for each bound it cannot evaluate."""
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

        def limit_of(name: str) -> float | None:
            spec = catalog.parameters.get(template_name(name))
            text = resolved.get(name, spec.default if spec is not None else None)
            return float(text) if text is not None and _LITERAL_NUMBER.match(text) else None

        for key, raw in set_here.items():
            spec = catalog.parameters.get(template_name(key))
            if spec is None or spec.value_kind not in ("integer", "scalar") or not _LITERAL_NUMBER.match(raw):
                continue
            value = float(raw)
            for bound, label, beyond in (
                (spec.minimum, "minimum", lambda v, b: v < b), (spec.maximum, "maximum", lambda v, b: v > b),
            ):
                if bound is None or _LITERAL_NUMBER.match(bound):
                    continue
                limit = limit_of(bound) if _PARAMETER_NAME.fullmatch(bound) else None
                if limit is None:
                    found.append(diagnostic(
                        "warning", "opencarp_bound_not_checked",
                        f"{key}: its {label} is {bound!r}, which omniD cannot evaluate against the case; "
                        "the bound was not checked",
                        source=document, field=key,
                    ))
                elif beyond(value, limit):
                    found.append(diagnostic(
                        "error", "catalog_rule",
                        f"{key} = {raw} is beyond its {label}, {bound} = {limit:g}",
                        source=document, field=key,
                    ))
    return tuple(found)
