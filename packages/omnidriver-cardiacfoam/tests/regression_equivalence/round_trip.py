"""Round-trip stability of the agent's dict layer (solver-free): ``build ∘ parse`` must be idempotent on its own output.

Parsed selectors are not compared: ``parse_electro_properties`` omits values equal to a catalog ``typical_value``, so only the generated text is stable.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from regression_equivalence.tutorials_tree import tutorials_root
from omnidriver.cardiacfoam.dict_builder import (
    build_electro_properties,
    parse_electro_properties,
)
from regression_equivalence.registry import RegressionCase


def _build_from_parse(path: Path) -> str:
    parsed = parse_electro_properties(path)
    return build_electro_properties(parsed["selectors"], overrides=parsed["overrides"])


def _write_temp(text: str) -> Path:
    with tempfile.NamedTemporaryFile(
        "w", suffix=".electroProperties", delete=False
    ) as fh:
        fh.write(text)
        return Path(fh.name)


def electro_build_parse_fixpoint(case: RegressionCase) -> tuple[str, str]:
    """Return (once, twice) generated electroProperties texts; equal means idempotent."""
    committed = tutorials_root() / case.case_dir / "constant/electroProperties"
    once = _build_from_parse(committed)
    tmp = _write_temp(once)
    try:
        twice = _build_from_parse(tmp)
    finally:
        tmp.unlink(missing_ok=True)
    return once, twice
