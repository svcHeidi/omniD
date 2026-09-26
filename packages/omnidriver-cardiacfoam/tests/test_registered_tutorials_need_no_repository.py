"""Registered tutorials must keep working when core stops inventing a root.

Measured 2026-09-04 before the change: 18 of 26 catalog entries build under an
arbitrary empty base, niederer2011 among them. The other 8 are 4 tutorials
plus case-folded aliases which read pre-existing case content -- one file and
one key, <case>/system/decomposeParDict's numberOfSubdomains -- because a
parallel solve changes the DAG's shape and the rank count cannot be invented.
Those 4 already failed identically before this work, since this repository has
no tutorials/ tree at all.

**Corrected 2026-09-24:** `heartSolverComparison` (2 of the original 26
entries -- itself and its case-folded alias) was deleted; it pointed at a
native case that does not exist in the authoritative native tree. 16 of the
remaining 24 catalog entries now build under an arbitrary empty base; the
other 8's identity is unchanged.

Both halves are pinned so the distinction stops being rediscovered.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.core.plugin_interface import load_plugin_context

_NEEDS_CASE_CONTENT = {
    "manufacturedbathbidomain",
    "manufacturedbidomain",
    "manufacturedeikonalecg",
    "manufacturedmonodomainpseudoecg",
}


def _factories():
    return load_plugin_context("cardiacfoam").capabilities.tutorials.catalog()[
        "spec_factories"
    ]


def test_niederer2011_builds_under_any_base(tmp_path: Path) -> None:
    spec = _factories()["niederer2011"](cases_root=tmp_path)
    assert Path(spec.case_root).is_relative_to(tmp_path)


def test_every_serial_tutorial_builds_under_any_base(tmp_path: Path) -> None:
    failed = []
    built = 0
    for index, (name, factory) in enumerate(sorted(_factories().items())):
        if name.casefold() in _NEEDS_CASE_CONTENT:
            continue
        # Index, not name: the catalog holds case-folded aliases
        # (cable1DCVConvergence and cable1dcvconvergence), which collide as
        # directory names on a case-insensitive filesystem such as macOS APFS.
        base = tmp_path / f"case{index}"
        base.mkdir()
        try:
            factory(cases_root=base)
            built += 1
        except Exception as exc:  # noqa: BLE001 -- report, do not mask
            failed.append(f"{name}: {type(exc).__name__}: {exc}")
    assert failed == [], "tutorials that stopped building under a plain base:\n" + "\n".join(failed)
    # Measured 2026-09-04; 16 after `heartSolverComparison`'s 2026-09-24
    # deletion removed 2 entries; 14 after `restitutionCurves`'s 2026-09-25
    # migration onto a tutorial record (docs/superpowers/specs/2026-09-24-
    # tutorials-are-pointers-design.md, step 4b) removed its own 2 (the
    # tutorial and its case-folded alias) from SPEC_FACTORIES -- it is no
    # longer a factory tutorial at all, so it is absent from `_factories()`
    # here, not merely unbuildable. A sweep that silently covered zero
    # tutorials would otherwise assert nothing.
    # Corrected 2026-09-26 (niederer2012 -> niederer2011 rename): registry.py
    # carried an extra, undocumented alias key, "niedereretal2012", mapped to
    # the same factory as CardiacTutorialID.NIEDERER_2012.value/.value.lower()
    # -- three keys for one tutorial. The rename drops that alias rather than
    # reproducing it under the new name (the old name must be refused like
    # any unknown entry, not kept reachable under either spelling), so
    # SPEC_FACTORIES now holds 13 buildable entries, not 14.
    assert built == 13, f"expected 13 buildable catalog entries, got {built}"


@pytest.mark.parametrize("name", sorted(_NEEDS_CASE_CONTENT))
def test_the_parallel_tutorials_still_ask_for_a_rank_count(name: str, tmp_path: Path) -> None:
    """The contrast is the point: without it, the sweep above would pass even
    if every tutorial had silently become content-dependent."""
    factory = {k.casefold(): v for k, v in _factories().items()}[name]
    with pytest.raises(ValueError, match="num_subdomains"):
        factory(cases_root=tmp_path)
