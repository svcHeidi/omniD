"""`apply_overrides()` applies through the case-write channel: it stages
every touched document into a private snapshot, describes the change as a
`CaseMutationRequest`/`ParameterAssignment` per override, and commits via
`case_transaction.commit_case_write`. Builds its own minimal catalog/context
rather than depending on the monorepo's real tutorial dicts.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from omnidriver.core.contracts.dictionary import DictEntry
from omnidriver.core.runtime.attempt_lease import acquire_case_lease
from omnidriver.openfoam.apply_overrides import (
    OverrideError,
    OverrideScope,
    RegenerationScope,
    apply_overrides,
)
from omnidriver.openfoam.effective_dictionary import EffectiveDictionaryResult
from omnidriver.openfoam.mutators import read_foam_entry


class _Catalog:
    def __init__(self, groups: dict[str, tuple]):
        self._groups = groups

    def entries_for(self, group: str) -> tuple:
        return self._groups.get(group, ())


def _context(
    *,
    control_dict_entries: tuple = (),
    scopes: tuple = (),
    regen_scopes: tuple = (),
    groups: dict | None = None,
) -> SimpleNamespace:
    all_groups = dict(groups or {})
    all_groups.setdefault("controlDict", control_dict_entries)
    return SimpleNamespace(
        capabilities=SimpleNamespace(
            dictionaries=SimpleNamespace(catalog=lambda: _Catalog(all_groups)),
            override_scopes=SimpleNamespace(scopes=lambda: scopes),
            dict_regeneration=SimpleNamespace(scopes=lambda: regen_scopes),
        ),
    )


def _control_dict_case(tmp_path: Path, text: str = "deltaT 0.001;\nendTime 1;\n") -> Path:
    (tmp_path / "system").mkdir()
    (tmp_path / "system" / "controlDict").write_text(text)
    return tmp_path


# --------------------------------------------------------------------------
# Parity: the same bytes land, through the new mechanism
# --------------------------------------------------------------------------


def test_apply_writes_the_same_bytes_with_no_execution_env(tmp_path):
    """The write-only path (no readback requested) writes case_root's
    directly-observable content and returns `()`."""
    case = _control_dict_case(tmp_path)
    context = _context(control_dict_entries=(
        DictEntry(driver_path="deltaT", description="time step", value_kind="scalar"),
    ))

    result = apply_overrides(
        [{"driver_path": "deltaT", "value": "0.0005"}],
        case_root=case, driver_context=context,
    )

    assert result == ()
    assert (case / "system" / "controlDict").read_text() == "deltaT    0.0005;\nendTime 1;\n"


def test_apply_preserves_the_original_spelling_verbatim(tmp_path):
    """A value that round-trips through parsing for the audit record must
    still be WRITTEN verbatim -- "1e-3" stays "1e-3" on disk, it does not
    become a re-rendered "0.001"."""
    case = _control_dict_case(tmp_path, "deltaT 0.001;\n")
    context = _context(control_dict_entries=(
        DictEntry(driver_path="deltaT", description="time step", value_kind="scalar"),
    ))
    apply_overrides(
        [{"driver_path": "deltaT", "value": "1e-3"}],
        case_root=case, driver_context=context,
    )
    assert "1e-3" in (case / "system" / "controlDict").read_text()
    assert "0.001" not in (case / "system" / "controlDict").read_text().replace("1e-3", "")


def test_apply_of_an_empty_override_list_is_a_no_op(tmp_path):
    """`clone_and_patch` requires >=1 parameter; an empty override list must
    stay a well-defined no-op, not attempt a zero-parameter request."""
    case = _control_dict_case(tmp_path)
    original = (case / "system" / "controlDict").read_bytes()
    context = _context()

    assert apply_overrides([], case_root=case, driver_context=context) == ()
    assert (case / "system" / "controlDict").read_bytes() == original


def test_apply_wraps_a_missing_target_as_override_error(tmp_path):
    """No controlDict at all: the mutator's FileNotFoundError must surface
    as OverrideError, not raw."""
    tmp_path.mkdir(exist_ok=True)
    context = _context(control_dict_entries=(
        DictEntry(driver_path="deltaT", description="time step", value_kind="scalar"),
    ))
    with pytest.raises(OverrideError):
        apply_overrides(
            [{"driver_path": "deltaT", "value": "0.0005"}],
            case_root=tmp_path, driver_context=context,
        )


def test_a_failure_partway_through_a_batch_leaves_case_root_completely_untouched(tmp_path):
    """Two overrides, the second fails (an unknown controlDict key raises
    KeyError from the structured editor). case_root is never written at
    all until every override in the batch has staged successfully."""
    case = _control_dict_case(tmp_path, "deltaT 0.001;\n")
    original = (case / "system" / "controlDict").read_bytes()
    context = _context(control_dict_entries=(
        DictEntry(driver_path="deltaT", description="d", value_kind="scalar"),
        DictEntry(driver_path="writeInterval", description="d", value_kind="scalar"),
    ))

    with pytest.raises(OverrideError):
        apply_overrides(
            [
                {"driver_path": "deltaT", "value": "0.0005"},
                # writeInterval is catalog-known (validate_overrides accepts
                # it) but absent from this controlDict -> KeyError at write
                # time, from the structured editor fallback.
                {"driver_path": "writeInterval", "value": "5"},
            ],
            case_root=case, driver_context=context,
        )

    assert (case / "system" / "controlDict").read_bytes() == original


# --------------------------------------------------------------------------
# New under the channel: precondition drift is refused, not silently
# overwritten
# --------------------------------------------------------------------------


def test_a_change_between_precondition_capture_and_commit_refuses_the_apply(tmp_path, monkeypatch):
    """`commit_case_write`'s precondition recheck refuses a concurrent edit
    rather than silently overwriting it. Simulated deterministically by
    monkeypatching `patch_preconditions` to mutate case_root immediately
    after it captures the (still-correct) before-digest, standing in for a
    race that would otherwise need real concurrency to observe."""
    case = _control_dict_case(tmp_path, "deltaT 0.001;\nendTime 1;\n")
    control_dict = case / "system" / "controlDict"
    context = _context(control_dict_entries=(
        DictEntry(driver_path="deltaT", description="d", value_kind="scalar"),
    ))

    from omnidriver.openfoam import case_rendering as case_rendering_module

    real_patch_preconditions = case_rendering_module.patch_preconditions
    racing_text = "deltaT 0.001;\nendTime 999;\n"

    def _racing_patch_preconditions(resolved, **kwargs):
        preconditions = real_patch_preconditions(resolved, **kwargs)
        control_dict.write_text(racing_text)
        return preconditions

    monkeypatch.setattr(case_rendering_module, "patch_preconditions", _racing_patch_preconditions)

    with pytest.raises(OverrideError, match="changed since the plan was made"):
        apply_overrides(
            [{"driver_path": "deltaT", "value": "0.0005"}],
            case_root=case, driver_context=context,
        )

    # The race's own edit survives untouched: the apply was refused outright,
    # not partially applied over it.
    assert control_dict.read_text() == racing_text


def test_environment_precondition_is_a_genuine_second_consumer(tmp_path, monkeypatch):
    """`--apply` reading a dict with a real `#includeEtc` directive must
    produce `environment` preconditions -- proving this is a genuine call
    site, not a mocked assertion that the function was merely invoked."""
    case = _control_dict_case(tmp_path, "deltaT 0.001;\n")
    control_dict = case / "system" / "controlDict"
    control_dict.write_text('#includeEtc "controlDict"\n' + control_dict.read_text())
    context = _context(control_dict_entries=(
        DictEntry(driver_path="deltaT", description="d", value_kind="scalar"),
    ))

    from omnidriver.openfoam import case_rendering as case_rendering_module

    captured: dict = {}
    real_patch_preconditions = case_rendering_module.patch_preconditions

    def _capturing_patch_preconditions(resolved, **kwargs):
        preconditions = real_patch_preconditions(resolved, **kwargs)
        captured["preconditions"] = preconditions
        return preconditions

    monkeypatch.setattr(case_rendering_module, "patch_preconditions", _capturing_patch_preconditions)

    apply_overrides(
        [{"driver_path": "deltaT", "value": "0.0005"}],
        case_root=case, driver_context=context,
        execution_env={"WM_PROJECT_DIR": "/opt/openfoam-does-not-exist"},
    )

    kinds = {p.kind for p in captured["preconditions"]}
    assert "environment" in kinds, (
        f"expected an environment precondition from the #includeEtc closure; "
        f"got {captured['preconditions']}"
    )


# --------------------------------------------------------------------------
# `:`-path (system/<file>:<entry>) route: uncatalogued, type-inferred
# --------------------------------------------------------------------------


def test_apply_file_path_route_still_works_without_a_catalog_entry(tmp_path):
    (tmp_path / "system").mkdir()
    (tmp_path / "system" / "fvSolution").write_text("solvers { V { tolerance 1e-5; } }\n")
    context = _context()

    apply_overrides(
        [{"driver_path": "system/fvSolution:solvers/V/tolerance", "value": "1e-6"}],
        case_root=tmp_path, driver_context=context,
    )

    tolerance = read_foam_entry(
        tmp_path / "system" / "fvSolution", "tolerance", scope=["solvers", "V"],
    )
    assert float(tolerance) == pytest.approx(1e-6)


def test_apply_file_path_route_refuses_a_value_with_no_closed_shape(tmp_path):
    """This route has no catalog entry to supply a `value_kind`, so a
    value this module cannot classify (here: a string containing
    whitespace, neither a number nor a single word) is refused rather
    than silently written."""
    (tmp_path / "system").mkdir()
    (tmp_path / "system" / "fvSchemes").write_text(
        "ddtSchemes { default Euler; }\n"
    )
    context = _context()

    with pytest.raises(OverrideError):
        apply_overrides(
            [{"driver_path": "system/fvSchemes:ddtSchemes/default", "value": "Crank Nicolson"}],
            case_root=tmp_path, driver_context=context,
        )


# --------------------------------------------------------------------------
# Regeneration scopes: structural rewrite through a snapshot
# --------------------------------------------------------------------------


def test_regeneration_scope_writes_through_a_snapshot(tmp_path):
    (tmp_path / "constant").mkdir()
    electro = tmp_path / "constant" / "electro"
    electro.write_text("solver oldSolver;\n")

    def regenerate(path, dp, value, extra_overrides):
        del dp, extra_overrides
        path.write_text(f"solver {value};\n")

    regen_scope = RegenerationScope(
        selector_keys=frozenset({"mySolver"}), file_relpath="constant/electro",
        catalog_group="electro", regenerate=regenerate,
    )
    context = _context(
        groups={"electro": (
            DictEntry(
                driver_path="mySolver", description="d", value_kind="enum",
                enum_values=("oldSolver", "newSolver"),
            ),
        )},
        regen_scopes=(regen_scope,),
    )

    apply_overrides(
        [{"driver_path": "mySolver", "value": "newSolver"}],
        case_root=tmp_path, driver_context=context,
    )
    assert electro.read_text() == "solver newSolver;\n"


def test_regeneration_failure_leaves_case_root_untouched(tmp_path):
    """`regenerate()` runs against the snapshot copy, never `case_root`
    directly -- a raise from it must leave the real file exactly as it was."""
    (tmp_path / "constant").mkdir()
    electro = tmp_path / "constant" / "electro"
    electro.write_text("solver oldSolver;\n")
    original = electro.read_text()

    def regenerate(path, dp, value, extra_overrides):
        del extra_overrides
        if value == "badSolver":
            raise ValueError(f"{dp}={value} is not a supported coupling")
        path.write_text(f"solver {value};\n")

    regen_scope = RegenerationScope(
        selector_keys=frozenset({"mySolver"}), file_relpath="constant/electro",
        catalog_group="electro", regenerate=regenerate,
    )
    context = _context(
        groups={"electro": (
            DictEntry(
                driver_path="mySolver", description="d", value_kind="enum",
                enum_values=("oldSolver", "newSolver", "badSolver"),
            ),
        )},
        regen_scopes=(regen_scope,),
    )

    with pytest.raises(OverrideError, match="not a supported coupling"):
        apply_overrides(
            [{"driver_path": "mySolver", "value": "badSolver"}],
            case_root=tmp_path, driver_context=context,
        )
    assert electro.read_text() == original


def test_regeneration_receives_the_extra_overrides_from_the_same_batch(tmp_path):
    """`extra_overrides` -- the other `$TOKEN.`-scoped overrides in this
    same call that target the regeneration scope's own file -- must reach
    `regenerate()`."""
    (tmp_path / "constant").mkdir()
    electro = tmp_path / "constant" / "electro"
    electro.write_text("solver oldSolver;\nfoo old;\n")

    seen: dict = {}

    def regenerate(path, dp, value, extra_overrides):
        del dp
        seen["extra_overrides"] = dict(extra_overrides)
        path.write_text(f"solver {value};\nfoo {extra_overrides.get('$ELECTRO.foo', 'old')};\n")

    regen_scope = RegenerationScope(
        selector_keys=frozenset({"mySolver"}), file_relpath="constant/electro",
        catalog_group="electro", regenerate=regenerate,
    )
    scope = OverrideScope(
        token="ELECTRO", file_relpath="constant/electro", catalog_group="electro",
        resolve_entry=lambda dp, root: (None, "foo"),
    )
    context = _context(
        groups={"electro": (
            DictEntry(
                driver_path="mySolver", description="d", value_kind="enum",
                enum_values=("oldSolver", "newSolver"),
            ),
            DictEntry(driver_path="$ELECTRO.foo", description="d", value_kind="word"),
        )},
        scopes=(scope,), regen_scopes=(regen_scope,),
    )

    apply_overrides(
        [
            {"driver_path": "mySolver", "value": "newSolver"},
            {"driver_path": "$ELECTRO.foo", "value": "bar"},
        ],
        case_root=tmp_path, driver_context=context,
    )

    assert seen["extra_overrides"] == {"$ELECTRO.foo": "bar"}
    # update_foam_entry re-patches "foo" after regenerate() already wrote it
    # (same value, harmless) -- its own "key    value;" spacing convention,
    # not regenerate()'s "foo {value};" spelling, is what survives.
    assert read_foam_entry(electro, "foo") == "bar"
    assert electro.read_text().splitlines()[0] == "solver newSolver;"


def test_scope_resolve_entry_sees_a_prior_regeneration_in_the_same_batch(tmp_path):
    """Within a single `apply_overrides()` call, a later override's
    `scope.resolve_entry` must see what an earlier override in the same
    call already wrote, not the pristine, pre-batch case_root -- mirrors
    cardiacFoam's real `resolve_entry`, which detects the active
    `<solver>Coeffs` block by reading `constant/electroProperties`."""
    (tmp_path / "constant").mkdir()
    electro = tmp_path / "constant" / "electro"
    electro.write_text(
        "solver oldSolver;\n"
        "oldSolverCoeffs\n{\n    x 1;\n}\n"
        "newSolverCoeffs\n{\n    x 2;\n}\n"
    )

    def regenerate(path, dp, value, extra_overrides):
        del dp, extra_overrides
        text = path.read_text()
        path.write_text(text.replace("solver oldSolver;", f"solver {value};"))

    def resolve_entry(dp, root):
        active = read_foam_entry(root / "constant" / "electro", "solver")
        return ([f"{active}Coeffs"], dp.split(".", 1)[1])

    regen_scope = RegenerationScope(
        selector_keys=frozenset({"mySolver"}), file_relpath="constant/electro",
        catalog_group="electro", regenerate=regenerate,
    )
    scope = OverrideScope(
        token="ELECTRO", file_relpath="constant/electro", catalog_group="electro",
        resolve_entry=resolve_entry,
    )
    context = _context(
        groups={"electro": (
            DictEntry(
                driver_path="mySolver", description="d", value_kind="enum",
                enum_values=("oldSolver", "newSolver"),
            ),
            DictEntry(driver_path="$ELECTRO.x", description="d", value_kind="integer"),
        )},
        scopes=(scope,), regen_scopes=(regen_scope,),
    )

    apply_overrides(
        [
            {"driver_path": "mySolver", "value": "newSolver"},
            {"driver_path": "$ELECTRO.x", "value": 42},
        ],
        case_root=tmp_path, driver_context=context,
    )

    assert read_foam_entry(electro, "x", scope=["newSolverCoeffs"]) == "42"
    assert read_foam_entry(electro, "x", scope=["oldSolverCoeffs"]) == "1"


# --------------------------------------------------------------------------
# case_lease_held threading
# --------------------------------------------------------------------------


def test_apply_reuses_an_already_held_case_lease(tmp_path):
    """`--apply` reached via `cli.py` already holds the case lease for the
    whole `step` (`_dispatch_context`) before `apply_overrides()` runs.
    `commit_case_write`'s own lease is not reentrant, so `apply_overrides()`
    must detect the held lease and pass `case_lease_held=True` rather than
    try to acquire a second one."""
    case = _control_dict_case(tmp_path)
    context = _context(control_dict_entries=(
        DictEntry(driver_path="deltaT", description="d", value_kind="scalar"),
    ))

    with acquire_case_lease(case):
        apply_overrides(
            [{"driver_path": "deltaT", "value": "0.0005"}],
            case_root=case, driver_context=context,
        )

    assert "0.0005" in (case / "system" / "controlDict").read_text()


def test_apply_acquires_its_own_lease_when_none_is_held(tmp_path):
    """The ordinary case (a standalone call): no lease held beforehand,
    `commit_case_write` acquires and releases its own."""
    case = _control_dict_case(tmp_path)
    context = _context(control_dict_entries=(
        DictEntry(driver_path="deltaT", description="d", value_kind="scalar"),
    ))

    apply_overrides(
        [{"driver_path": "deltaT", "value": "0.0005"}],
        case_root=case, driver_context=context,
    )

    assert "0.0005" in (case / "system" / "controlDict").read_text()
    # The lease was released, not left held, once the call returned.
    with acquire_case_lease(case):
        pass


# --------------------------------------------------------------------------
# The pre-channel helpers are genuinely gone
# --------------------------------------------------------------------------


def test_the_pre_channel_direct_write_helpers_are_removed():
    import omnidriver.openfoam.apply_overrides as module

    assert not hasattr(module, "_restore_on_failure")
    assert not hasattr(module, "_apply_validated_overrides")


# --------------------------------------------------------------------------
# Readback against the real OpenFOAM install, not a fixture
# --------------------------------------------------------------------------


def test_apply_readback_matches_the_real_foamdictionary(tmp_path):
    """Verified against a real, sourced OpenFOAM install, not a
    monkeypatched resolver. A requested "1e-3" must resolve through the
    real `foamDictionary` as "0.001" and still be reported as a match:
    values are compared, not spellings."""
    from omnidriver.openfoam.openfoam_environment import (
        discover_openfoam_bashrc,
        load_openfoam_environment,
    )

    bashrc = discover_openfoam_bashrc()
    if bashrc is None:
        pytest.skip("no real OpenFOAM install discoverable on this machine")

    openfoam_env = load_openfoam_environment(bashrc_path=bashrc)
    if openfoam_env.error or "PATH" not in openfoam_env.env:
        pytest.skip(f"could not source the real OpenFOAM environment: {openfoam_env.error}")

    case = _control_dict_case(tmp_path, "deltaT 0.001;\nendTime 1;\n")
    context = _context(control_dict_entries=(
        DictEntry(driver_path="deltaT", description="d", value_kind="scalar"),
    ))

    evidence = apply_overrides(
        [{"driver_path": "deltaT", "value": "1e-3"}],
        case_root=case, driver_context=context,
        execution_env=openfoam_env.env,
    )

    assert len(evidence) == 1
    assert evidence[0]["status"] == "resolved"
    assert evidence[0]["parser"] == "foamDictionary"
    # The real foamDictionary re-serialises "1e-3" as "0.001" -- confirming
    # values are compared, not text, over a real native parse.
    assert evidence[0]["value"] == "0.001"
    assert evidence[0]["matches_requested"] is True
    # The file on disk keeps the original spelling regardless -- the native
    # re-serialisation above is what foamDictionary reports back, not what
    # was written.
    assert "1e-3" in (case / "system" / "controlDict").read_text()
