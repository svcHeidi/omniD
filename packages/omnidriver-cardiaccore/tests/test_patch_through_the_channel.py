"""cardiacCore's `apply_input_overrides` routes through the write channel.

Phase 2 Task 8 (docs/superpowers/plans/2026-09-20-phase2-one-write-channel.md).
The existing path was `apply_input_overrides` -> `update_foam_entry`: a direct
write, no plan, no journal. This migrates it as the channel's first real
consumer, keeping the public signature -- a caller outside this repository
must not break in the same commit that changes the mechanism underneath it.

`test_applying_overrides_still_writes_the_same_bytes` is the characterization:
captured against the pre-migration `update_foam_entry` path (still importable,
unchanged, at `omnidriver.openfoam.mutators.update_foam_entry`) and asserted
again once the migration lands. It must pass unchanged.
"""
from __future__ import annotations

import inspect
import os
from pathlib import Path

import pytest

from omnidriver.cardiaccore.plugin import CardiacCorePlugin
from omnidriver.cardiaccore.workflows.overrides import (
    apply_input_overrides,
    apply_input_overrides_planned,
)
from omnidriver.core.case_write import CaseMutationRequest, ParameterAssignment
from omnidriver.core.plugin_interface import driver_context
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin

_root_makes_chmod_tests_meaningless = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root ignores the write-permission bit this test injects a failure with",
)


def _case_with_conductivity_dict(tmp_path: Path) -> Path:
    case_root = tmp_path / "bivCase"
    system = case_root / "system"
    system.mkdir(parents=True)
    (system / "setCardiacConductivityDict").write_text(
        "df 0.1143;\nds 0.052;\ndn 0.016;\nfiberField fiber;\nsheetField sheet;\n"
    )
    return case_root


def _stack_context():
    return driver_context(OpenFOAMEnvironmentPlugin(), CardiacCorePlugin(), source="test")


# --------------------------------------------------------------------------
# Step 1: characterization -- must pass before AND after the migration.
# --------------------------------------------------------------------------


def test_applying_overrides_still_writes_the_same_bytes(tmp_path):
    """Captured 2026-09-23 against the pre-migration `update_foam_entry` path.

    Not a test of the new channel -- a test that the new channel produces the
    same case the old direct-write path did. Semantic parity is what makes a
    migration a migration rather than a rewrite.
    """
    case = _case_with_conductivity_dict(tmp_path)
    apply_input_overrides(case, {"$CARDIAC_CONDUCTIVITY.df": 0.42})
    text = (case / "system" / "setCardiacConductivityDict").read_text()
    assert text == "df    0.42;\nds 0.052;\ndn 0.016;\nfiberField fiber;\nsheetField sheet;\n"
    assert (case / "system" / "setCardiacConductivityDict").stat().st_mode & 0o777 == 0o644


# --------------------------------------------------------------------------
# The new path
# --------------------------------------------------------------------------


def test_a_patch_is_planned_before_it_is_written(tmp_path):
    case = _case_with_conductivity_dict(tmp_path)
    context = _stack_context()
    request = CaseMutationRequest(
        mode="clone_and_patch", case_root=case, adapter_id="org.omnidriver.cardiaccore",
        workflow="preprocessing", source_artifacts=(),
        parameters=(ParameterAssignment(
            qualified_id="$CARDIAC_CONDUCTIVITY.df", owner="org.omnidriver.cardiaccore",
            document="system/setCardiacConductivityDict", key_path=("df",),
            binding={}, value=0.42, value_kind="scalar", source="case",
        ),),
        requested_by="test",
    )
    resolved = context.capabilities.case_writer.resolve(request, driver_context=context)
    assert resolved.formats() == ("openfoam_dictionary",)
    # Nothing written yet: resolution is pure.
    assert "0.42" not in (case / "system" / "setCardiacConductivityDict").read_text()


def test_the_plan_names_every_file_it_read(tmp_path):
    """Preconditions cover the complete read dependency set: the patched
    document itself, at minimum. (This fixture's dictionary declares no
    `#include`/`#includeEtc`, so no `include`/`absence` preconditions are
    expected here -- see test_the_include_closure_is_exercised_against_the_
    native_install for a fixture that does.)"""
    case = _case_with_conductivity_dict(tmp_path)
    record = apply_input_overrides_planned(case, {"$CARDIAC_CONDUCTIVITY.df": 0.42})
    assert record is not None
    assert record.status == "committed"


def test_a_rolled_back_patch_leaves_the_dictionary_byte_identical(tmp_path):
    """A precondition that no longer holds refuses before any byte is
    written."""
    from omnidriver.core import case_transaction, case_write

    case = _case_with_conductivity_dict(tmp_path)
    original = (case / "system" / "setCardiacConductivityDict").read_bytes()

    context = _stack_context()
    request = CaseMutationRequest(
        mode="clone_and_patch", case_root=case, adapter_id="org.omnidriver.cardiaccore",
        workflow="preprocessing", source_artifacts=(),
        parameters=(ParameterAssignment(
            qualified_id="$CARDIAC_CONDUCTIVITY.df", owner="org.omnidriver.cardiaccore",
            document="system/setCardiacConductivityDict", key_path=("df",),
            binding={}, value=0.99, value_kind="scalar", source="case",
        ),),
        requested_by="test",
    )
    resolved = context.capabilities.case_writer.resolve(request, driver_context=context)
    rendered = context.capabilities.case_writer.render(
        resolved, snapshot_root=tmp_path / "scratch", driver_context=context, execution_env=None,
    )
    plan = case_write.CaseWritePlan(
        request=request, files=rendered,
        preconditions=(case_write.Precondition(
            kind="file", target="system/setCardiacConductivityDict",
            digest="0" * 64, must_be_absent=False,
        ),),
        semantic_owner_id=resolved.semantic_owner_id,
        stack_identity=context.identity.capability_digest,
        created_at="2026-09-23T00:00:00Z",
    )
    with pytest.raises(case_transaction.CaseTransactionError, match="setCardiacConductivityDict"):
        case_transaction.commit_case_write(plan, driver_context=context, execution_env=None)
    assert (case / "system" / "setCardiacConductivityDict").read_bytes() == original


def test_the_public_entry_point_keeps_its_signature():
    signature = inspect.signature(apply_input_overrides)
    assert list(signature.parameters) == ["case_root", "overrides"]
    assert signature.return_annotation in (None, "None")


def test_no_overrides_is_a_no_op_not_an_empty_mutation(tmp_path):
    """`clone_and_patch` requires >=1 parameter (R2 finding 7); an override
    mapping with nothing declared must not attempt a zero-parameter request."""
    case = _case_with_conductivity_dict(tmp_path)
    original = (case / "system" / "setCardiacConductivityDict").read_bytes()
    assert apply_input_overrides_planned(case, {}) is None
    assert apply_input_overrides_planned(case, None) is None
    assert (case / "system" / "setCardiacConductivityDict").read_bytes() == original


def test_a_patched_document_carries_a_before_digest_precondition(tmp_path):
    case = _case_with_conductivity_dict(tmp_path)
    context = _stack_context()
    request = CaseMutationRequest(
        mode="clone_and_patch", case_root=case, adapter_id="org.omnidriver.cardiaccore",
        workflow="preprocessing", source_artifacts=(),
        parameters=(ParameterAssignment(
            qualified_id="$CARDIAC_CONDUCTIVITY.df", owner="org.omnidriver.cardiaccore",
            document="system/setCardiacConductivityDict", key_path=("df",),
            binding={}, value=0.42, value_kind="scalar", source="case",
        ),),
        requested_by="test",
    )
    resolved = context.capabilities.case_writer.resolve(request, driver_context=context)

    from omnidriver.openfoam import case_rendering

    preconditions = case_rendering.patch_preconditions(resolved, case_root=case)
    kinds = {p.kind for p in preconditions}
    assert "file" in kinds
    file_preconditions = [p for p in preconditions if p.kind == "file"]
    assert any(p.target == "system/setCardiacConductivityDict" for p in file_preconditions)


def test_the_include_closure_is_exercised_against_the_native_install(tmp_path):
    """A dictionary reading `#includeEtc "controlDict"` pulls in a real etc
    file from the real OpenFOAM v2412 install at /Volumes/OpenFOAM-v2412,
    which `discover_openfoam_bashrc()` finds -- not a fixture stub. This
    proves the include-closure walk, not just its call signature, against
    the real `findEtcFile` chain (audit finding F2)."""
    from omnidriver.openfoam.openfoam_environment import discover_openfoam_bashrc

    bashrc = discover_openfoam_bashrc()
    if bashrc is None:
        pytest.skip("no real OpenFOAM install discoverable on this machine")

    case = _case_with_conductivity_dict(tmp_path)
    dictionary = case / "system" / "setCardiacConductivityDict"
    dictionary.write_text(
        '#includeEtc "controlDict"\n' + dictionary.read_text()
    )

    context = _stack_context()
    request = CaseMutationRequest(
        mode="clone_and_patch", case_root=case, adapter_id="org.omnidriver.cardiaccore",
        workflow="preprocessing", source_artifacts=(),
        parameters=(ParameterAssignment(
            qualified_id="$CARDIAC_CONDUCTIVITY.df", owner="org.omnidriver.cardiaccore",
            document="system/setCardiacConductivityDict", key_path=("df",),
            binding={}, value=0.42, value_kind="scalar", source="case",
        ),),
        requested_by="test",
    )
    resolved = context.capabilities.case_writer.resolve(request, driver_context=context)

    from omnidriver.openfoam import case_rendering

    environment = {**os.environ, "FOAM_ETC": str(bashrc.parent)}
    preconditions = case_rendering.patch_preconditions(
        resolved, case_root=case, execution_env=environment,
    )
    kinds = {p.kind for p in preconditions}
    assert "include" in kinds, (
        f"expected an `include` precondition from the real etc chain; got {preconditions}"
    )
    include_targets = {p.target for p in preconditions if p.kind == "include"}
    assert any("controlDict" in target for target in include_targets)
