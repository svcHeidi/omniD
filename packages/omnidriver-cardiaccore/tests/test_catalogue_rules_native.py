"""cardiacCore's catalogue relations, run on the resolved case of the real native
records before anything executes: every record plans clean, and a study that
breaks a relation is refused by name with the catalogue's own message."""
from __future__ import annotations

import pytest

from cardiaccore_native import TARGETS, native_cardiaccore_anatomy, native_cardiaccore_tree
from omnidriver.core.plugin_interface import load_plugin_context
from omnidriver.core.strict_planning import strict_plan
from omnidriver.core.tutorial_records import TutorialRecordError

pytestmark = pytest.mark.native_cardiaccore


def _plan(record: str, tmp_path, study: dict | None = None):
    inputs = {"anatomy": str(native_cardiaccore_anatomy())} if record == "humanSlab" else None
    return strict_plan(
        record, overrides={"cases_root": str(native_cardiaccore_tree()), **(study or {})},
        scratch_root=tmp_path / "scratch", inputs=inputs, driver_context=load_plugin_context("cardiaccore"),
    )


@pytest.mark.parametrize("record", sorted(TARGETS))
def test_every_record_plans_clean(record, tmp_path):
    report = _plan(record, tmp_path)
    assert report.status == "ok", [d.message for d in report.validation_diagnostics + report.artifact_diagnostics]


def test_half_a_bidomain_conductivity_pair_is_refused_before_it_runs(tmp_path):
    with pytest.raises(TutorialRecordError) as exc:
        _plan("idealizedHeart", tmp_path, {"system/setCardiacConductivityDict:conductivityIntracellular.df": 0.2})
    message = str(exc.value)
    assert "tutorial record 'idealizedHeart': the resolved case breaks" in message
    assert "conductivityIntracellular.df requires conductivityExtracellular.dn to be set as well." in message
