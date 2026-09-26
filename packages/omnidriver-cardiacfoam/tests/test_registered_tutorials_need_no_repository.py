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
    # "manufacturedbathbidomain" removed 2026-09-26: migrated onto a tutorial
    # record (records/manufactured_bath_bidomain.py, step 5.4a), for the same
    # reason as "manufacturedbidomain" below.
    # "manufacturedbidomain" removed 2026-09-26: migrated onto a tutorial
    # record (records/manufactured_bidomain.py, tutorials-are-pointers plan,
    # step 5.4b-B) -- it is no longer in SPEC_FACTORIES/`_factories()` at
    # all, so it can neither be skipped here nor asked for a rank count
    # below; a record run's parallel/serial choice is the OpenFOAM layer's
    # job (owner Q6), not this factory-era gate's.
    # "manufacturedeikonalecg" removed 2026-09-26: migrated onto a tutorial
    # record (records/manufactured_eikonal_ecg.py, step 5.4b-E), for the same
    # reason as "manufacturedbidomain" above.
    "manufacturedmonodomainpseudoecg",
}


def _factories():
    return load_plugin_context("cardiacfoam").capabilities.tutorials.catalog()[
        "spec_factories"
    ]


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
    # SPEC_FACTORIES held 13 buildable entries, not 14.
    # Corrected 2026-09-26 (5.4b-N): niederer2011 migrated onto a tutorial
    # record (records/niederer_2011.py) and left SPEC_FACTORIES entirely --
    # its single key (already all-lowercase, so its own ".lower()" alias line
    # was always the same key) is simply gone, not merely unbuildable, so the
    # buildable count drops by 1, to 12.
    # Corrected 2026-09-26 (`manufacturedEikonalECG`'s migration onto a
    # tutorial record, records/manufactured_eikonal_ecg.py): its 2 keys
    # (case and case-folded) are gone from SPEC_FACTORIES too, the same way
    # `restitutionCurves`'s were -- but it was one of `_NEEDS_CASE_CONTENT`,
    # so those 2 keys were already excluded from `built`, not counted in it.
    # The count stays 12.
    # Corrected 2026-09-26 (5.4a, `manufacturedBathBidomain` onto a tutorial
    # record): likewise one of `_NEEDS_CASE_CONTENT`, so the count stays 12.
    assert built == 12, f"expected 12 buildable catalog entries, got {built}"


@pytest.mark.parametrize("name", sorted(_NEEDS_CASE_CONTENT))
def test_the_parallel_tutorials_still_ask_for_a_rank_count(name: str, tmp_path: Path) -> None:
    """The contrast is the point: without it, the sweep above would pass even
    if every tutorial had silently become content-dependent."""
    factory = {k.casefold(): v for k, v in _factories().items()}[name]
    # Corrected 2026-09-26 (PAR): matched "num_subdomains", the name of a
    # fallback count no caller passed; it is deleted, and the refusal names
    # the file the count is read from.
    with pytest.raises(ValueError, match="system/decomposeParDict"):
        factory(cases_root=tmp_path)
