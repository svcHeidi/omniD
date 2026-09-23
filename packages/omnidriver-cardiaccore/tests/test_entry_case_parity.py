"""Byte-level characterization: `plan_case` must write exactly what
`apply_case` writes, for every cardiacCore preprocessing spec migrated in
Phase 2 Task 10 (docs/superpowers/plans/2026-09-20-phase2-one-write-channel.md).

The plan's own Task 10 names `packages/omnidriver/tests/core/
test_entry_case_parity.py` as this test's location -- but every spec Task 10
migrates lives in `omnidriver-cardiaccore`, which core tests must not import
(the import-boundary rule is enforced by
`scripts/check-import-boundaries.py` with an empty waiver list). Corrected
2026-09-23: the plumbing test (preference, fallback, deprecation warning)
lives in core's own `test_entry_case_parity.py`, exercising only synthetic
specs; this file carries the actual byte-level parity evidence.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from omnidriver.cardiaccore.workflows.preprocessing import (
    make_human_purkinje_endocardial_spec,
    make_human_purkinje_slab_spec,
    make_pig_morphometric_purkinje_spec,
    make_pig_transmural_purkinje_spec,
)


def _write_biv_dictionaries(case_root: Path) -> None:
    system = case_root / "system"
    system.mkdir(parents=True)
    (system / "setCardiacConductivityDict").write_text(
        "df 0.1143;\nds 0.052;\ndn 0.016;\nfiberField fiber;\nsheetField sheet;\n"
    )
    (system / "setCardiacAnatomyDict").write_text(
        "zApicalMid 0.3333333;\nzMidBasal 0.6666667;\nzApexCap 0.08;\n"
    )
    (system / "setPurkinjeSlabDict").write_text("thickness 0.1;\nmultiplier 3.0;\n")
    (system / "setPurkinjeMorphometryDict").write_text("")
    (system / "generatePurkinjeTreeDict").write_text(
        "growthModel surfaceFollow;\n"
        "hisBundleSeed (0.014 0.022 -0.007);\n"
        "lv\n{\n    seed (0.011 0.019 -0.002);\n    N_it 24;\n}\n"
        "rv\n{\n    seed (0.016 0.025 -0.012);\n    N_it 32;\n}\n"
    )


def _digests(case_root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(case_root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(case_root.rglob("*"))
        if path.is_file() and ".omnidriver" not in path.parts
    }


_MAKE_SPECS = {
    "human_purkinje_slab": make_human_purkinje_slab_spec,
    "human_purkinje_endocardial": make_human_purkinje_endocardial_spec,
    "pig_morphometric_purkinje": make_pig_morphometric_purkinje_spec,
    "pig_transmural_purkinje": make_pig_transmural_purkinje_spec,
}

_OVERRIDES = {
    "$CARDIAC_CONDUCTIVITY.df": 0.2,
}


def _run(make_spec, case_root: Path, *, use_plan_case: bool) -> dict[str, str]:
    _write_biv_dictionaries(case_root)
    spec = make_spec(cases_root=case_root.parent, input_overrides=dict(_OVERRIDES))
    case = spec.build_cases()[0]
    if use_plan_case:
        record = spec.plan_case(case_root, case)
        assert record is not None
        assert record.status == "committed"
    else:
        spec.apply_case(case_root, case)
    return _digests(case_root)


def test_every_migrated_spec_has_a_plan_case():
    for name, make_spec in _MAKE_SPECS.items():
        spec = make_spec(cases_root=Path("/tmp/unused"))
        assert spec.plan_case is not None, f"{name} has no plan_case"


def test_plan_case_writes_byte_identical_content_to_apply_case(tmp_path):
    for name, make_spec in _MAKE_SPECS.items():
        apply_root = tmp_path / name / "apply" / "bivCase"
        plan_root = tmp_path / name / "plan" / "bivCase"

        apply_digests = _run(make_spec, apply_root, use_plan_case=False)
        plan_digests = _run(make_spec, plan_root, use_plan_case=True)

        assert plan_digests == apply_digests, f"{name}: plan_case diverged from apply_case"
