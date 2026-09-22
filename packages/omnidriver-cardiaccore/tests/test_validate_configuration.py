"""``validate_configuration`` checks the full catalog against the resolved
case at plan time -- not just what a given tutorial's ``active_input_paths``
exposes as overridable.

Regression gate for the CARDIACCORE_RETIREMENT_REVIEW_2026-09-16.md finding
that this hook returned an empty tuple unconditionally. A Purkinje-*tree*
tutorial's ``active_input_paths`` (see ``PURKINJE_TREE_INPUT_PATHS`` in
workflows/preprocessing.py) omits the bidomain
``conductivityIntracellular``/``conductivityExtracellular`` pair the catalog
itself declares co-required (catalogs/inputs.py) -- so a half-set pair in
the resolved case went unreported until a RunDocument happened to expose it
at run/step time. These tests write that half-set pair directly and prove
this hook catches it before that point.
"""

from pathlib import Path

from omnidriver.cardiaccore.plugin import CardiacCorePlugin
from omnidriver.cardiaccore.workflows.preprocessing import (
    make_human_purkinje_endocardial_spec,
)


def _write_conductivity_dict(case_root: Path, *, bidomain_intracellular_only: bool) -> None:
    system = case_root / "system"
    system.mkdir(parents=True, exist_ok=True)
    body = (
        "df 0.1;\n"
        "ds 0.05;\n"
        "dn 0.05;\n"
        "fiberField f;\n"
        "sheetField s;\n"
    )
    if bidomain_intracellular_only:
        # A genuine "half-set" bidomain pair: intracellular declared,
        # extracellular entirely absent -- exactly the FatalIOError shape
        # setCardiacConductivity.C guards against (see catalogs/inputs.py's
        # co_required_with comment on this group).
        body += "conductivityIntracellular\n{\n    df 0.1;\n}\n"
    (system / "setCardiacConductivityDict").write_text(body)


def _write_anatomy_dict(case_root: Path) -> None:
    system = case_root / "system"
    system.mkdir(parents=True, exist_ok=True)
    (system / "setCardiacAnatomyDict").write_text(
        "zApicalMid 0.3;\nzMidBasal 0.6;\nzApexCap 0.1;\n"
    )


def test_a_half_set_bidomain_pair_outside_active_input_paths_is_now_reported(tmp_path):
    spec = make_human_purkinje_endocardial_spec(cases_root=tmp_path)
    _write_conductivity_dict(Path(spec.case_root), bidomain_intracellular_only=True)
    _write_anatomy_dict(Path(spec.case_root))

    diagnostics = CardiacCorePlugin().validate_configuration(spec)

    messages = " ".join(d.message for d in diagnostics)
    assert "conductivityIntracellular.df" in messages
    assert "requires" in messages
    assert any(d.level == "error" for d in diagnostics)


def test_a_fully_set_or_fully_absent_bidomain_pair_reports_nothing(tmp_path):
    spec = make_human_purkinje_endocardial_spec(cases_root=tmp_path)
    _write_conductivity_dict(Path(spec.case_root), bidomain_intracellular_only=False)
    _write_anatomy_dict(Path(spec.case_root))

    assert CardiacCorePlugin().validate_configuration(spec) == ()


def test_generic_case_folder_entries_are_not_checked_against_this_catalog(tmp_path):
    """A case_folder run with this plugin merely active, not a cardiacCore
    preprocessing tutorial, declares none of this catalog -- see
    test_generic_contract.py::test_controlled_allrun_executes_without_domain_claims,
    which this hook must not break."""
    spec = make_human_purkinje_endocardial_spec(cases_root=tmp_path)
    spec.metadata["generic_case"] = True
    # Deliberately no case files written at all -- a generic case is
    # exempt regardless of what is or is not on disk.

    assert CardiacCorePlugin().validate_configuration(spec) == ()
