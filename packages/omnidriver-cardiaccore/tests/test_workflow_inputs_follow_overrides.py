"""One resolution of the effective configuration feeds everything.

Two consequences of resolving inputs more than once, or not at all:

* A requested conductivity field name came back as `None`, because a
  scar-dictionary entry with the same leaf name collided with it under the
  unqualified slot key and the absent scar document's `None` won. No
  diagnostic was raised -- the caller was told the write succeeded.
* The workflow DAG's `consumes` named `0/fiber` and `0/sheet` literally, so a
  case renaming those fields declared inputs it does not read and omitted the
  ones it does.

`resolve_workflow_inputs` resolves once; staging, validation, DAG edges and
provenance all read that one answer.

**Corrected 2026-09-22 (batch G0-C):** the plan this file implements
(`docs/superpowers/plans/2026-09-22-phase2-prerequisites.md`, Task 6 Step 2)
also specified a test asserting that a case with no dictionaries at all
produces an error-level diagnostic from `build_config`. Measured against the
actual code: `read_foam_entry` returns `None` for a missing file rather than
raising, so `read_input_values` never raises for an absent case either --
every declared path simply resolves to `None` and `resolve_workflow_inputs`
correctly treats that as "nothing to report", not as an error. The
`except (FileNotFoundError, KeyError, ValueError, RuntimeError)` guard this
function inherits from the pre-existing `build_config` is defensive against a
genuinely malformed dictionary (unparseable content), not an absent one, and
no such fixture exists yet in this test suite (the standing rule here is a
real case or a drift gate, nothing invented). That test was omitted rather
than kept failing against a premise the code does not hold.
"""

from pathlib import Path

from omnidriver.cardiaccore.workflows.preprocessing import (
    make_human_purkinje_slab_spec,
)
from omnidriver.cardiaccore.workflows.run_config import build_config


def _case(root: Path, **overrides) -> object:
    spec = make_human_purkinje_slab_spec(cases_root=root, input_overrides=overrides or None)
    system = Path(spec.case_root) / "system"
    system.mkdir(parents=True, exist_ok=True)
    (system / "setCardiacConductivityDict").write_text(
        "df 0.1;\nds 0.05;\ndn 0.05;\nfiberField f;\nsheetField s;\n"
    )
    (system / "setCardiacAnatomyDict").write_text(
        "zApicalMid 0.3;\nzMidBasal 0.6;\nzApexCap 0.1;\n"
    )
    return spec


def test_a_requested_field_name_is_not_replaced_by_none(tmp_path):
    spec = _case(tmp_path, **{"$CARDIAC_CONDUCTIVITY.fiberField": "myFibre"})
    config, diagnostics = build_config(spec)
    assert not [d for d in diagnostics if d.level == "error"], diagnostics
    assert config["preprocessing"]["$CARDIAC_CONDUCTIVITY.fiberField"] == "myFibre"


def test_an_absent_document_does_not_overwrite_a_present_one(tmp_path):
    """The scar dictionary is not in this case at all. Its absence must not
    reach into the conductivity dictionary's slot."""
    spec = _case(tmp_path)
    config, _ = build_config(spec)
    assert config["preprocessing"]["$CARDIAC_CONDUCTIVITY.fiberField"] == "f"
    assert "$CARDIAC_SCAR.fiberField" not in config["preprocessing"]


def test_the_dag_consumes_the_field_names_the_case_will_use(tmp_path):
    spec = _case(tmp_path, **{
        "$CARDIAC_CONDUCTIVITY.fiberField": "myFibre",
        "$CARDIAC_CONDUCTIVITY.sheetField": "mySheet",
    })
    steps = {step["id"]: step for step in spec.metadata["workflow_dag"]["steps"]}
    consumes = steps["conductivity"]["consumes"]
    assert "0/myFibre" in consumes
    assert "0/mySheet" in consumes
    assert "0/fiber" not in consumes
    assert "0/sheet" not in consumes


def test_the_default_field_names_are_unchanged_without_an_override(tmp_path):
    spec = _case(tmp_path)
    steps = {step["id"]: step for step in spec.metadata["workflow_dag"]["steps"]}
    consumes = steps["conductivity"]["consumes"]
    assert "0/fiber" in consumes
    assert "0/sheet" in consumes


def test_the_dag_consumes_feeds_the_resume_fingerprint(tmp_path):
    """The DAG defect was real for the resume/provenance path too:
    `provenance_inputs._collect_consumed_relpaths` reads `step["consumes"]`
    directly off the same `workflow_dag` object this spec builds, so a
    renamed conductivity field is only tracked for resume if the DAG's
    `consumes` list names it. Settled by evidence (see Task 6 Step 7's grep
    of `provenance_inputs.py`), not assumed.
    """
    from omnidriver.core.runtime.provenance_inputs import _collect_consumed_relpaths

    spec = _case(tmp_path, **{"$CARDIAC_CONDUCTIVITY.fiberField": "myFibre"})
    relpaths = _collect_consumed_relpaths(spec.metadata["workflow_dag"])
    assert "0/myFibre" in relpaths
    assert "0/fiber" not in relpaths
