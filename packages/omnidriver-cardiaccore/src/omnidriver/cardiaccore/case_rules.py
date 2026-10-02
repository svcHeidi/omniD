"""cardiacCore's catalogue relations, run over the utility dictionaries a
resolved case holds."""

from __future__ import annotations

from pathlib import Path

from omnidriver.core.planning_types import StrictDiagnostic, diagnostic
from omnidriver.openfoam.case_rules import read_leaves, rule_diagnostics

from .catalogs.inputs import CATALOG


def case_diagnostics(case_root: Path) -> tuple[StrictDiagnostic, ...]:
    found: list[StrictDiagnostic] = []
    for name, entries in CATALOG.documents.items():
        path = Path(case_root) / "system" / name
        if not path.is_file():
            continue
        try:
            leaves = read_leaves(path)
        except (OSError, ValueError, KeyError) as exc:
            found.append(diagnostic(
                "error", "case_unreadable", f"{path} cannot be read: {exc}",
                source=f"system/{name}",
            ))
            continue
        found += rule_diagnostics(entries, leaves, document=f"system/{name}")
    return tuple(found)
