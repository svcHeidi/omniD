"""Tests for the catalogue relations (``case_rules``) and the cross-field rules over a flat context.

``_filled_run`` supplies every required ``$ELECTRO_MODEL_COEFFS.*`` leaf so a test isolates validator behaviour."""

from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.dict_entries import DictEntry
from omnidriver.cardiacfoam.dict_entries_catalog import ELECTRO_PROPERTY_ENTRY_GROUPS
from omnidriver.cardiacfoam.common_dict_entries import PHYSICS_PROPERTY_ENTRIES, PURKINJE_GRAPH_ENTRIES
from omnidriver.openfoam.control_dict import CONTROL_DICT_ENTRIES
from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
from omnidriver.core.planning_types import StrictDiagnostic
from omnidriver.cardiacfoam.validation import cross_field_diagnostics
from omnidriver.core.contracts.catalogue_paths import slot_key
from omnidriver.openfoam.case_rules import rule_diagnostics

_CTX = _driver_context(OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(), source="test:validation")


def _validate(config, *, entries=None, driver_context):
    """The catalogue relations over the flat context the per-phase slices make."""
    context = {key: val for slice_ in config.values() for key, val in slice_.items() if val not in (None, "")}
    if entries is None:
        # controlDict and the Purkinje graph are documents of their own, judged by their own rules.
        entries = [
            e for e in driver_context.stack.call("get_dict_entries")
            if e not in CONTROL_DICT_ENTRIES and e not in PURKINJE_GRAPH_ENTRIES
        ]
    return tuple(rule_diagnostics(entries, context, document="constant/electroProperties"))

_PHASE_ORDER = ("anatomy", "physics", "stimulus", "solver")


def _cross_field(config):
    return cross_field_diagnostics({
        key: value for slice_ in config.values() for key, value in slice_.items()
        if value not in (None, "")
    })


def _catalogue_rules(run):
    from omnidriver.cardiacfoam.record_key_validation import _ELECTRO_ENTRIES_BY_PATH
    from omnidriver.openfoam.case_rules import rule_diagnostics

    return rule_diagnostics(_ELECTRO_ENTRIES_BY_PATH.values(), {
        key: value for slice_ in run.values() for key, value in slice_.items()
        if value not in (None, "")
    }, document="constant/electroProperties")


def _all_entries():
    yield from PHYSICS_PROPERTY_ENTRIES
    yield from CONTROL_DICT_ENTRIES
    for group in ELECTRO_PROPERTY_ENTRY_GROUPS.values():
        yield from group


def _blank_run(**overrides) -> dict:
    config: dict[str, dict] = {
        "anatomy": {}, "physics": {}, "stimulus": {}, "solver": {},
    }
    for ph, slice_ in overrides.get("config", {}).items():
        config.setdefault(ph, {}).update(slice_)
    return config


class TestSlotKeyScopeTokenStripping:
    """slot_key strips any "$TOKEN." shape, not only the scope token the cardiac plugin declares."""

    def test_strips_the_cardiac_scope_token(self) -> None:
        assert slot_key("$ELECTRO_MODEL_COEFFS.myocardiumSolver") == "myocardiumSolver"

    def test_strips_an_arbitrary_scope_token_of_the_same_shape(self) -> None:
        assert slot_key("$SOME_OTHER_PLUGIN_COEFFS.foo.bar") == "foo.bar"

    def test_leaves_an_unprefixed_path_unchanged(self) -> None:
        assert slot_key("myocardiumSolver") == "myocardiumSolver"

    def test_leaves_a_dollar_sign_not_matching_the_scope_token_shape_unchanged(self) -> None:
        # No trailing "." after an all-caps run, so not the $TOKEN. convention.
        assert slot_key("$notAToken") == "$notAToken"


def _filled_run(**overrides) -> dict:
    """A Run with every required leaf-name pre-populated with a plausible stub."""
    config: dict[str, dict] = {
        "anatomy": {}, "physics": {}, "stimulus": {}, "solver": {},
    }
    for e in _all_entries():
        is_unconditionally_required = e.required and not e.required_when
        is_conditionally_required = e.required_when and any(
            (lambda vals: config.get(ph2, {}).get(k) in (vals if isinstance(vals, tuple) else (vals,)))(v)
            for k, v in e.required_when.items()
            for ph2 in _PHASE_ORDER
        )
        if not (is_unconditionally_required or is_conditionally_required):
            continue
        ph = next((p for p in _PHASE_ORDER if p in e.phases), None)
        if ph is None:
            continue
        config.setdefault(ph, {})
        key = slot_key(e.driver_path)
        if e.value_kind == "enum" and e.enum_values:
            config[ph][key] = e.enum_values[0]
        else:
            config[ph][key] = "stub"
    for ph, slice_ in overrides.get("config", {}).items():
        config.setdefault(ph, {}).update(slice_)
    # The enum_values[0] fill can pair e.g. AlievPanfilov with epicardialCells,
    # which the tissue-compatibility rule rejects, so match tissue to ionicModel.
    from omnidriver.cardiacfoam.ionic_model_catalog import IONIC_MODEL_CATALOG
    phys = config.get("physics", {})
    model = phys.get("ionicModel")
    if model and "tissue" in phys:
        entry = IONIC_MODEL_CATALOG.get(model)
        if entry and entry.compatible_tissues and phys["tissue"] not in entry.compatible_tissues:
            phys["tissue"] = entry.compatible_tissues[0]
    return config


def test_empty_run_reports_missing_required_fields():
    errors = _validate(_blank_run(), driver_context=_CTX)
    assert any(e.field == "myocardiumSolver" and "is required" in e.message for e in errors)
    assert all(isinstance(e, StrictDiagnostic) for e in errors)


def test_valid_minimal_run_has_no_errors():
    run = _filled_run()
    errors = [e for e in _validate(run, driver_context=_CTX) if e.level == "error"]
    assert errors == [], f"expected no errors, got: {errors}"


@pytest.mark.parametrize(
    "write_control",
    # OpenFOAM v2412 `Foam::Time::writeControlNames`. The native bathBidomain
    # controlDict uses adjustableRunTime and a real cardiacFoam run accepts it
    # (see docs/solver-learning/cardiacfoam.md).
    ["none", "timeStep", "runTime", "adjustable", "adjustableRunTime", "clockTime", "cpuTime"],
)
def test_every_upstream_write_control_is_accepted(write_control):
    run = _filled_run(config={"solver": {"writeControl": write_control}})
    errors = [e for e in _validate(run, driver_context=_CTX)
              if e.level == "error" and e.field == "writeControl"]
    assert errors == []


def test_personalized_templates_valid_contract_is_accepted():
    from omnidriver.cardiacfoam.validation import _evaluate_personalized_templates

    prefix = "ecgDomains.ECG."
    template = prefix + "personalizedTemplates."
    context = {
        prefix + "ecgSolver": "eikonalECG",
        "ionicHeterogeneity.mode": "namedRegions",
        template + "ionicModelConfig.ionicModel": "TWorldcompactBatched",
        template + "ionicModelConfig.singleCellStimulus.stim_start": 20,
        template + "ionicModelConfig.singleCellStimulus.stim_period_S1": 1000,
        template + "ionicModelConfig.singleCellStimulus.stim_duration": 1,
        template + "ionicModelConfig.singleCellStimulus.stim_amplitude": 60,
        template + "nBeats": 10,
        template + "duration": 0.6,
        template + "dt": 1e-4,
        template + "ionicModelConfig.singleCellStimulus.nstim2": 0,
    }
    assert _evaluate_personalized_templates(context) == []


def test_a_configured_personalized_templates_block_must_set_the_keys_the_catalogue_requires_of_it():
    from omnidriver.cardiacfoam.record_key_validation import _ELECTRO_ENTRIES_BY_PATH
    from omnidriver.cardiacfoam.validation import infer_virtual_presence
    from omnidriver.openfoam.case_rules import rule_diagnostics

    def judge(context):
        context = dict(context)
        infer_virtual_presence(context)
        return sorted(
            item.field for item in rule_diagnostics(
                tuple(_ELECTRO_ENTRIES_BY_PATH.values()), context, document="constant/electroProperties",
            ) if "personalizedTemplates" in item.field
        )

    case = {
        "ecgDomains.A.ecgSolver": "eikonalECG", "ecgDomains.B.ecgSolver": "eikonalECG",
        "ecgDomains.A.personalizedTemplates.nBeats": 3,
    }
    assert judge(case) == sorted(
        "ecgDomains.A.personalizedTemplates." + leaf for leaf in (
            "ionicModelConfig.ionicModel", "duration", "dt",
            "ionicModelConfig.singleCellStimulus.stim_start",
            "ionicModelConfig.singleCellStimulus.stim_period_S1",
            "ionicModelConfig.singleCellStimulus.stim_duration",
            "ionicModelConfig.singleCellStimulus.stim_amplitude",
        )
    )
    assert judge({k: v for k, v in case.items() if "personalizedTemplates" not in k}) == []


def test_personalized_templates_rejects_manufactured_ecg_before_execution():
    from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
    from omnidriver.cardiacfoam.validation import _evaluate_personalized_templates

    prefix = "ecgDomains.ECG."
    context = {
        prefix + "ecgSolver": "eikonalECG",
        prefix + "personalizedTemplates.nBeats": 1,
        prefix + "verificationModel.type": "manufacturedEikonalECGVerifier",
    }
    errors = _evaluate_personalized_templates(context)
    assert any("cannot be combined" in error.message for error in errors)
    diagnostics = cross_field_diagnostics(context)
    assert any("cannot be combined" in error.message for error in diagnostics)


def _ecg_context(*, tissue_type: str, anisotropic: str) -> dict:
    return {
        "verificationModel.type": tissue_type,
        "ecgDomains.ECG.verificationModel.type": "manufacturedPseudoECGVerifier",
        "ecgDomains.ECG.verificationModel.anisotropic": anisotropic,
    }


def test_ecg_anisotropic_matches_anisotropic_tissue_verifier_passes():
    from omnidriver.cardiacfoam.validation import _evaluate_ecg_anisotropic_consistency

    context = _ecg_context(
        tissue_type="manufacturedAnisotropicMonodomainVerifier",
        anisotropic="yes",
    )
    assert _evaluate_ecg_anisotropic_consistency(context) == []
    assert cross_field_diagnostics(context) == []


def test_ecg_anisotropic_matches_isotropic_tissue_verifier_passes():
    from omnidriver.cardiacfoam.validation import _evaluate_ecg_anisotropic_consistency

    context = _ecg_context(
        tissue_type="manufacturedFDAMonodomainVerifier",
        anisotropic="no",
    )
    assert _evaluate_ecg_anisotropic_consistency(context) == []
    assert cross_field_diagnostics(context) == []


def test_ecg_anisotropic_no_rejected_when_tissue_verifier_is_anisotropic():
    """The mismatch found in the native case: anisotropic left `no` (or unset) under the anisotropic verifier."""
    from omnidriver.cardiacfoam.validation import _evaluate_ecg_anisotropic_consistency

    context = _ecg_context(
        tissue_type="manufacturedAnisotropicMonodomainVerifier",
        anisotropic="no",
    )
    errors = _evaluate_ecg_anisotropic_consistency(context)
    assert len(errors) == 1
    assert errors[0].field == "ecgDomains.ECG.verificationModel.anisotropic"
    assert "must be yes" in errors[0].message

    diagnostics = cross_field_diagnostics(context)
    assert any("must be yes" in d.message for d in diagnostics)


def test_ecg_anisotropic_yes_rejected_when_tissue_verifier_is_not_anisotropic():
    from omnidriver.cardiacfoam.validation import _evaluate_ecg_anisotropic_consistency

    context = _ecg_context(
        tissue_type="manufacturedFDAMonodomainVerifier",
        anisotropic="yes",
    )
    errors = _evaluate_ecg_anisotropic_consistency(context)
    assert len(errors) == 1
    assert errors[0].field == "ecgDomains.ECG.verificationModel.anisotropic"
    assert "must match the tissue verifier" in errors[0].message

    diagnostics = cross_field_diagnostics(context)
    assert any("must match the tissue verifier" in d.message for d in diagnostics)


def test_batched_integrator_does_not_constrain_active_tension_model():
    """Batched active-tension models always use explicit Euler and never read it (``batchedActiveTensionModel::advanceSubstep``)."""
    from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin

    for model in (
        "LandNiedererBatched",
        "LandNiedererTWorldBatched",
        "NashPanfilovBatched",
    ):
        diagnostics = cross_field_diagnostics({
            "activeTensionModel": model,
            "batchedIntegrator": "rushLarsen",
        })
        assert not [d for d in diagnostics if d.field == "batchedIntegrator"]


def test_constraint_violation_is_flagged():
    # eikonalSolver disallows an explicit ionicModel.
    run = _filled_run(config={
        "physics": {
            "myocardiumSolver": "eikonalSolver",
            "ionicModel": "tenTusscher2006",
        },
    })
    errors = _validate(run, driver_context=_CTX)
    assert any("eikonal" in e.message.lower() for e in errors), (
        f"expected an eikonal-related error, got: {[e.message for e in errors]}"
    )


# -------- Structured constraint evaluation --------
#
# These tests use synthesized DictEntry fixtures rather than the live
# catalog so the assertions stay stable independently of catalog changes.


def _entry(driver_path: str, **overrides) -> DictEntry:
    defaults = {
        "driver_path": driver_path,
        "description": "fixture",
        "value_kind": "word",
        "source_refs": ("ref.C",),
        "phases": frozenset({"physics"}),
    }
    defaults.update(overrides)
    return DictEntry(**defaults)


def test_forbidden_when_flags_violation_in_run():
    """forbidden_when matches AND entry value is set in context → error."""
    entry = _entry(
        "$ELECTRO_MODEL_COEFFS.ionicModel",
        forbidden_when={"myocardiumSolver": "eikonalSolver"},
    )
    run = _blank_run(config={"physics": {
        "myocardiumSolver": "eikonalSolver",
        "ionicModel": "TNNP",
    }})
    errors = _validate(run, entries=[entry], driver_context=_CTX)
    forbidden_errors = [e for e in errors if "forbidden" in e.message.lower()]
    assert len(forbidden_errors) == 1, (
        f"expected exactly one forbidden_when violation, got: "
        f"{[e.message for e in errors]}"
    )
    assert "myocardiumSolver" in forbidden_errors[0].message
    assert "eikonalSolver" in forbidden_errors[0].message


def test_forbidden_when_silent_when_predicate_doesnt_match():
    entry = _entry(
        "$ELECTRO_MODEL_COEFFS.ionicModel",
        forbidden_when={"myocardiumSolver": "eikonalSolver"},
    )
    run = _blank_run(config={"physics": {
        "myocardiumSolver": "monodomainSolver",
        "ionicModel": "TNNP",
    }})
    errors = _validate(run, entries=[entry], driver_context=_CTX)
    forbidden_errors = [e for e in errors if "forbidden" in e.message.lower()]
    assert forbidden_errors == []


def test_required_when_flags_missing_value():
    entry = _entry(
        "$ELECTRO_MODEL_COEFFS.singleCellStimulus.stim_amplitude",
        required_when={"myocardiumSolver": "singleCellSolver"},
        phases=frozenset({"stimulus"}),
    )
    run = _blank_run(config={"physics": {
        "myocardiumSolver": "singleCellSolver",
    }})
    errors = _validate(run, entries=[entry], driver_context=_CTX)
    required_errors = [
        e for e in errors
        if "required" in e.message.lower() and "stim_amplitude" in e.message
    ]
    assert len(required_errors) == 1, (
        f"expected one required_when violation, got: {[e.message for e in errors]}"
    )


def test_required_when_silent_when_value_present():
    entry = _entry(
        "$ELECTRO_MODEL_COEFFS.singleCellStimulus.stim_amplitude",
        required_when={"myocardiumSolver": "singleCellSolver"},
        phases=frozenset({"stimulus"}),
    )
    run = _blank_run(config={
        "physics": {"myocardiumSolver": "singleCellSolver"},
        "stimulus": {"singleCellStimulus.stim_amplitude": "60"},
    })
    errors = _validate(run, entries=[entry], driver_context=_CTX)
    assert errors == ()


def test_required_when_silent_when_predicate_doesnt_match():
    entry = _entry(
        "$ELECTRO_MODEL_COEFFS.singleCellStimulus.stim_amplitude",
        required_when={"myocardiumSolver": "singleCellSolver"},
        phases=frozenset({"stimulus"}),
    )
    run = _blank_run(config={"physics": {
        "myocardiumSolver": "monodomainSolver",
    }})
    errors = _validate(run, entries=[entry], driver_context=_CTX)
    assert errors == ()


def test_applicable_when_skips_inapplicable_entry():
    """Skipped entirely: even required=True does not fire."""
    entry = _entry(
        "$ELECTRO_MODEL_COEFFS.bidomainOnlyKey",
        required=True,
        applicable_when={"myocardiumSolver": "bidomainSolver"},
    )
    run = _blank_run(config={"physics": {
        "myocardiumSolver": "monodomainSolver",
    }})
    errors = _validate(run, entries=[entry], driver_context=_CTX)
    assert errors == (), (
        f"inapplicable entry must not fire required check, got: "
        f"{[e.message for e in errors]}"
    )


def test_mutually_exclusive_with_flags_violation():
    """mutually_exclusive_with takes full driver_path or slot_key form; leaf-only names would collide across groups."""
    entry_a = _entry(
        "$ELECTRO_MODEL_COEFFS.externalStimulus.stimulusDuration",
        mutually_exclusive_with=(
            "$ELECTRO_MODEL_COEFFS.externalStimulus.stimulusDurationList",
        ),
        phases=frozenset({"stimulus"}),
    )
    entry_b = _entry(
        "$ELECTRO_MODEL_COEFFS.externalStimulus.stimulusDurationList",
        phases=frozenset({"stimulus"}),
    )
    run = _blank_run(config={"stimulus": {
        "externalStimulus.stimulusDuration": "0.002",
        "externalStimulus.stimulusDurationList": "(0.002 0.001)",
    }})
    errors = _validate(run, entries=[entry_a, entry_b], driver_context=_CTX)
    mutex_errors = [e for e in errors if "mutually exclusive" in e.message.lower()]
    assert len(mutex_errors) >= 1, (
        f"expected mutually-exclusive violation, got: {[e.message for e in errors]}"
    )


def test_tuple_predicate_matches_membership():
    entry = _entry(
        "$ELECTRO_MODEL_COEFFS.manufacturedCoeff",
        applicable_when={"ionicModel": (
            "monodomainFDAManufactured",
            "bidomainFDAManufactured",
            "bathBidomainFDAManufactured",
        )},
        required=True,
    )
    run_inactive = _blank_run(config={"physics": {"ionicModel": "TNNP"}})
    assert _validate(run_inactive, entries=[entry], driver_context=_CTX) == ()

    run_active = _blank_run(config={"physics": {
        "ionicModel": "monodomainFDAManufactured",
    }})
    errors = _validate(run_active, entries=[entry], driver_context=_CTX)
    required_errors = [e for e in errors if "required" in e.message.lower()]
    assert len(required_errors) >= 1


def test_applicable_when_matches_a_scope_prefixed_predicate_key():
    """applicable_when keys carry the scope token; it is stripped before comparing against slot_key context."""
    from omnidriver.openfoam.case_rules import applicable_entries

    entry = _entry(
        "$ELECTRO_MODEL_COEFFS.gatedByPrefixedKey",
        applicable_when={
            "$ELECTRO_MODEL_COEFFS.verificationModel.type": (
                "manufacturedFDABidomainVerifier",
            ),
        },
    )
    inactive = applicable_entries([entry], {"verificationModel.type": "manufacturedEikonalVerifier"})
    assert inactive == []

    active = applicable_entries([entry], {"verificationModel.type": "manufacturedFDABidomainVerifier"})
    assert active == [entry]


def test_applicable_when_matches_a_dynamic_placeholder_sibling_key():
    """A ``<name>`` placeholder in a sibling predicate key matches any configured instance name."""
    from omnidriver.openfoam.case_rules import applicable_entries

    entry = _entry(
        "$ELECTRO_MODEL_COEFFS.conductionNetworkDomains.<name>."
        "purkinjeGraphModelCoeffs.useEdgeConductance",
        applicable_when={
            "$ELECTRO_MODEL_COEFFS.conductionNetworkDomains.<name>."
            "purkinjeGraphModelCoeffs.conductionSystemSolver": (
                "restitutionEikonalSolver1D",
            ),
        },
    )
    inactive = applicable_entries([entry], {
            "conductionNetworkDomains.purkinjeNetwork.purkinjeGraphModelCoeffs"
            ".conductionSystemSolver": "eikonalSolver1D",
        })
    assert inactive == []

    active = applicable_entries([entry], {
            "conductionNetworkDomains.purkinjeNetwork.purkinjeGraphModelCoeffs"
            ".conductionSystemSolver": "restitutionEikonalSolver1D",
        })
    assert active == [entry]


def test_validate_run_accepts_default_entries_for_backward_compat():
    """With no ``entries`` kwarg, validate_context uses the live catalog."""
    run = _filled_run()
    errors = [e for e in _validate(run, driver_context=_CTX) if e.level == "error"]
    assert errors == []


# -------- Solver-coupling evaluator --------
#
# conductionSystemSolver, electroDomainCoupler and conductionNetworkDomain fit
# no DictEntry family; their rules live in SOLVER_COMPATIBILITY_RULES.


def _coupling_run(myocardium: str, *,
                  purkinje: str | None = None,
                  coupler: str | None = None,
                  network_name: str = "purkinjeNet",
                  coupling_name: str = "lvCoupling") -> dict:
    """A run with the selected solver and optional Purkinje pairing; dynamic keys go in the physics slice."""
    config: dict[str, dict] = {
        "anatomy": {}, "physics": {}, "stimulus": {}, "solver": {},
    }
    config["physics"]["myocardiumSolver"] = myocardium
    if purkinje is not None:
        config["physics"][
            f"conductionNetworkDomains.{network_name}."
            f"purkinjeGraphModelCoeffs.conductionSystemSolver"
        ] = purkinje
        # A network counts as declared once any sub-key exists under it.
        config["physics"][
            f"conductionNetworkDomains.{network_name}.purkinjeGraphModelCoeffs.someKey"
        ] = "x"
    if coupler is not None:
        config["physics"][
            f"domainCouplings.{coupling_name}.electroDomainCoupler"
        ] = coupler
        # A coupling references the network by name.
        config["physics"][
            f"domainCouplings.{coupling_name}.conductionNetworkDomain"
        ] = network_name
    return config


def test_solver_coupling_silent_when_no_purkinje_pairing():
    run = _coupling_run("monodomainSolver")
    errors = _cross_field(run)
    coupling_errors = [
        e for e in errors
        if "coupling" in e.message.lower() or "coupler" in e.message.lower()
    ]
    assert coupling_errors == []


def test_solver_coupling_valid_monodomain_pair_silent():
    """mono + monodomain1D + reactionDiffusionPvjCoupler emits no coupling error."""
    run = _coupling_run(
        "monodomainSolver",
        purkinje="monodomain1DSolver",
        coupler="reactionDiffusionPvjCoupler",
    )
    errors = _cross_field(run)
    coupling_errors = [
        e for e in errors
        if "incompatible" in e.message.lower()
        or "required_coupler" in e.message.lower()
    ]
    assert coupling_errors == [], (
        f"valid pair must not error, got: {[e.message for e in errors]}"
    )


def test_solver_coupling_flags_incompatible_mono_eikonal_pair():
    run = _coupling_run(
        "monodomainSolver",
        purkinje="eikonalSolver",
        coupler="reactionDiffusionPvjCoupler",
    )
    errors = _cross_field(run)
    incompat = [e for e in errors if "incompatible" in e.message.lower()]
    assert len(incompat) >= 1, (
        f"expected incompatible-pair error, got: {[e.message for e in errors]}"
    )


def test_solver_coupling_allows_bidomain_with_monodomain1D():
    run = _coupling_run(
        "bidomainSolver",
        purkinje="monodomain1DSolver",
        coupler="reactionDiffusionPvjCoupler",
    )
    errors = _cross_field(run)
    bidomain_errors = [
        e for e in errors
        if "bidomain" in e.message.lower() and "purkinje" in e.message.lower()
    ]
    assert len(bidomain_errors) == 0


def test_solver_coupling_flags_wrong_coupler_for_valid_pair():
    """The error cites the pair's required_coupler."""
    run = _coupling_run(
        "monodomainSolver",
        purkinje="monodomain1DSolver",
        coupler="eikonalPvjCoupler",   # wrong; should be reactionDiffusionPvjCoupler
    )
    errors = _cross_field(run)
    coupler_errors = [
        e for e in errors
        if "reactiondiffusionpvjcoupler" in e.message.lower()
    ]
    assert len(coupler_errors) >= 1, (
        f"expected error citing reactionDiffusionPvjCoupler, got: "
        f"{[e.message for e in errors]}"
    )


def _named_coupling_context():
    return {
        "myocardiumSolver": "monodomainSolver",
        "conductionNetworkDomains.a.purkinjeGraphModelCoeffs.conductionSystemSolver": "monodomain1DSolver",
        "conductionNetworkDomains.b.purkinjeGraphModelCoeffs.conductionSystemSolver": "eikonalSolver1D",
        "domainCouplings.left.conductionNetworkDomain": "a",
        "domainCouplings.left.electroDomainCoupler": "reactionDiffusionPvjCoupler",
        "domainCouplings.right.conductionNetworkDomain": "b",
        "domainCouplings.right.electroDomainCoupler": "eikonalMonodomainPvjCoupler",
    }


def test_solver_coupling_resolves_each_named_network_independent_of_order():
    from omnidriver.cardiacfoam.validation import _evaluate_solver_coupling

    context = _named_coupling_context()
    assert _evaluate_solver_coupling(context) == []
    assert _evaluate_solver_coupling(dict(reversed(list(context.items())))) == []


def test_solver_coupling_attributes_only_wrong_named_edge_independent_of_order():
    from omnidriver.cardiacfoam.validation import _evaluate_solver_coupling

    context = _named_coupling_context()
    context["domainCouplings.right.electroDomainCoupler"] = "reactionDiffusionPvjCoupler"
    errors = _evaluate_solver_coupling(context)
    assert errors == _evaluate_solver_coupling(dict(reversed(list(context.items()))))
    assert len(errors) == 1
    assert errors[0].field == "domainCouplings.right.electroDomainCoupler"
    assert errors[0].level == "error"
    assert "eikonalMonodomainPvjCoupler" in errors[0].message


def test_solver_coupling_uncovered_pair_is_explicit_warning_through_validate_context():
    run = _coupling_run(
        "monodomainSolver", purkinje="unreviewedNetworkSolver",
        coupler="reactionDiffusionPvjCoupler",
    )
    warnings = [
        item for item in _cross_field(run)
        if "compatibility is unknown" in item.message
    ]
    assert len(warnings) == 1
    assert warnings[0].level == "warning"
    assert warnings[0].field == "domainCouplings.lvCoupling.electroDomainCoupler"
    assert "unreviewedNetworkSolver" in warnings[0].message


def test_solver_coupling_missing_target_solver_does_not_borrow_sibling():
    from omnidriver.cardiacfoam.validation import _evaluate_solver_coupling

    context = _named_coupling_context()
    del context["conductionNetworkDomains.b.purkinjeGraphModelCoeffs.conductionSystemSolver"]
    context["conductionNetworkDomains.b.conductionSystemDomain"] = "purkinjeGraphModel"
    errors = _evaluate_solver_coupling(context)
    assert len(errors) == 1
    assert errors[0].field == "domainCouplings.right.electroDomainCoupler"
    assert errors[0].level == "warning"
    assert "compatibility is unknown" in errors[0].message


def test_solver_coupling_missing_selector_is_scoped_to_its_coupling():
    from omnidriver.cardiacfoam.validation import _evaluate_solver_coupling

    context = _named_coupling_context()
    del context["domainCouplings.right.electroDomainCoupler"]
    errors = _evaluate_solver_coupling(context)
    assert len(errors) == 1
    assert errors[0].field == "domainCouplings.right.electroDomainCoupler"
    assert "required" in errors[0].message


def test_solver_coupling_does_not_invent_edges_for_uncoupled_networks():
    from omnidriver.cardiacfoam.validation import _evaluate_solver_coupling

    context = _named_coupling_context()
    context = {key: value for key, value in context.items() if not key.startswith("domainCouplings.")}
    assert _evaluate_solver_coupling(context) == []


def test_solver_coupling_does_not_infer_missing_or_dangling_network_reference():
    from omnidriver.cardiacfoam.validation import _evaluate_solver_coupling

    for target in (None, "ghost"):
        context = _named_coupling_context()
        if target is None:
            del context["domainCouplings.right.conductionNetworkDomain"]
        else:
            context["domainCouplings.right.conductionNetworkDomain"] = target
        assert _evaluate_solver_coupling(context) == []


# -------- Block-reference evaluator --------


def test_block_reference_silent_when_no_couplings():
    run = _coupling_run("monodomainSolver")
    errors = _cross_field(run)
    ref_errors = [e for e in errors if "reference" in e.message.lower()]
    assert ref_errors == []


def test_block_reference_silent_when_target_block_declared():
    """A target counts as declared once any sub-key exists under conductionNetworkDomains.<name>."""
    run = _coupling_run(
        "monodomainSolver",
        purkinje="monodomain1DSolver",
        coupler="reactionDiffusionPvjCoupler",
        network_name="purkinjeNet",
        coupling_name="lvCoupling",
    )
    errors = _cross_field(run)
    dangling_errors = [
        e for e in errors
        if "reference" in e.message.lower()
        and ("not declared" in e.message.lower() or "dangling" in e.message.lower())
    ]
    assert dangling_errors == []


def test_block_reference_flags_dangling_target():
    config: dict[str, dict] = {
        "anatomy": {}, "physics": {}, "stimulus": {}, "solver": {},
    }
    config["physics"]["myocardiumSolver"] = "monodomainSolver"
    config["physics"][
        "domainCouplings.lvCoupling.conductionNetworkDomain"
    ] = "ghostNet"   # never declared under conductionNetworkDomains.ghostNet.*
    run = config

    errors = _cross_field(run)
    dangling = [
        e for e in errors
        if "ghostNet" in e.message
        and ("not declared" in e.message.lower()
             or "no matching" in e.message.lower())
    ]
    assert len(dangling) >= 1, (
        f"expected dangling-reference error for ghostNet, got: "
        f"{[e.message for e in errors]}"
    )


def test_dynamic_required_field_flags_missing_value_scoped_to_its_own_network():
    """purkinjeCV is required per network block: a sibling's solver neither satisfies nor triggers it."""
    config: dict[str, dict] = {
        "anatomy": {}, "physics": {}, "stimulus": {}, "solver": {},
    }
    config["physics"]["myocardiumSolver"] = "eikonalSolver"
    config["physics"][
        "conductionNetworkDomains.networkA.purkinjeGraphModelCoeffs"
        ".conductionSystemSolver"
    ] = "eikonalSolver1D"
    # networkA intentionally omits purkinjeCV.
    config["physics"][
        "conductionNetworkDomains.networkB.purkinjeGraphModelCoeffs"
        ".conductionSystemSolver"
    ] = "monodomain1DSolver"
    # networkB never needs purkinjeCV under this solver.
    run = config

    errors = _catalogue_rules(run)
    cv_errors = [e for e in errors if "purkinjeCV" in e.message]

    assert any("networkA" in e.message for e in cv_errors), (
        f"expected a missing-purkinjeCV error scoped to networkA, got: "
        f"{[e.message for e in errors]}"
    )
    assert not any("networkB" in e.message for e in cv_errors), (
        f"networkB must never be flagged for purkinjeCV -- it does not use "
        f"eikonalSolver1D: {[e.message for e in errors]}"
    )


"""Cross-fixture regression guard for validate_context.

For each of the 7 tutorial spec fixtures, build a representative config
that reflects the spec's solver type and assert that ``validate_context`` returns
zero *error*-level violations.

This catches accidentally over-restrictive structured constraints.
Warnings are permitted; only ``level="error"`` must be empty for each fixture run.

Fixture-to-solver mapping (derived from each spec's defaults.ELECTRO_PROPERTIES_SCOPE):
    single_cell          → singleCellSolver
    manufactured_monodomain_pseudo_ecg     → monodomainSolver  (ionic = monodomainFDAManufactured)
    manufactured_bidomain → bidomainSolver (ionic = bidomainFDAManufactured)
    manufactured_bath_bidomain → bidomainSolver (ionic = bathBidomainFDAManufactured)
    niederer_2011        → monodomainSolver  (ionic = TNNP, tissue = epicardialCells)
    restitution_curves   → singleCellSolver  (ionic = TNNP, tissue = epicardialCells)
    generic_case         → monodomainSolver  (representative; generic_case is
                           solver-agnostic, monodomainSolver is the most common)
"""


import pytest

from omnidriver.cardiacfoam.dict_entries_catalog import ELECTRO_PROPERTY_ENTRY_GROUPS
from omnidriver.cardiacfoam.common_dict_entries import PHYSICS_PROPERTY_ENTRIES
from omnidriver.openfoam.control_dict import CONTROL_DICT_ENTRIES
from omnidriver.core.contracts.catalogue_paths import slot_key
from omnidriver.openfoam.case_rules import rule_diagnostics

_PHASE_ORDER = ("anatomy", "physics", "stimulus", "solver")


def _all_entries():
    yield from PHYSICS_PROPERTY_ENTRIES
    yield from CONTROL_DICT_ENTRIES
    for group in ELECTRO_PROPERTY_ENTRY_GROUPS.values():
        yield from group


def _filled_run_for_solver(myocardium_solver: str, **extra_config) -> dict:
    """``_filled_run`` for one myocardiumSolver; ``extra_config`` maps phase to {slot_key: value}."""
    config: dict[str, dict] = {
        "anatomy": {}, "physics": {}, "stimulus": {}, "solver": {},
    }
    solver_context = {"myocardiumSolver": myocardium_solver, **extra_config.get("physics", {})}
    for e in _all_entries():
        is_unconditionally_required = e.required and not e.required_when
        is_conditionally_required = e.required_when and any(
            (lambda vals: solver_context.get(k) in (vals if isinstance(vals, tuple) else (vals,)))(v)
            for k, v in e.required_when.items()
        )
        if not (is_unconditionally_required or is_conditionally_required):
            continue
        ph = next((p for p in _PHASE_ORDER if p in e.phases), None)
        if ph is None:
            continue
        key = slot_key(e.driver_path)
        if e.value_kind == "enum" and e.enum_values:
            config[ph][key] = e.enum_values[0]
        else:
            config[ph][key] = "stub"

    config["physics"]["myocardiumSolver"] = myocardium_solver

    for ph, slice_ in extra_config.items():
        config.setdefault(ph, {}).update(slice_)

    return config


# ---------------------------------------------------------------------------
# Fixtures parameterised by spec name + representative run
# ---------------------------------------------------------------------------

# Each config matches its spec's actual solver and ionic model.

_FIXTURE_RUNS = [
    (
        "single_cell",
        _filled_run_for_solver(
            "singleCellSolver",
            physics={
                "type": "electroModel",
                "ionicModel": "TNNP",
                "tissue": "epicardialCells",
            },
        ),
    ),
    (
        "manufactured_monodomain_pseudo_ecg",
        _filled_run_for_solver(
            "monodomainSolver",
            physics={
                "type": "electroModel",
                "ionicModel": "monodomainFDAManufactured",
                # tissue not required for manufactured models (applicable_when excludes them)
            },
        ),
    ),
    (
        "manufactured_bidomain",
        _filled_run_for_solver(
            "bidomainSolver",
            physics={
                "type": "electroModel",
                "ionicModel": "bidomainFDAManufactured",
            },
        ),
    ),
    (
        "manufactured_bath_bidomain",
        _filled_run_for_solver(
            "bidomainSolver",
            physics={
                "type": "electroModel",
                "ionicModel": "bathBidomainFDAManufactured",
            },
        ),
    ),
    (
        "niederer_2011",
        _filled_run_for_solver(
            "monodomainSolver",
            physics={
                "type": "electroModel",
                "ionicModel": "TNNP",
                "tissue": "epicardialCells",
            },
        ),
    ),
    (
        "restitution_curves",
        _filled_run_for_solver(
            "singleCellSolver",
            physics={
                "type": "electroModel",
                "ionicModel": "TNNP",
                "tissue": "epicardialCells",
            },
        ),
    ),
    (
        "generic_case",
        _filled_run_for_solver(
            "monodomainSolver",
            physics={
                "type": "electroModel",
                "ionicModel": "TNNP",
                "tissue": "epicardialCells",
            },
        ),
    ),
]


@pytest.mark.parametrize("spec_label,run", _FIXTURE_RUNS, ids=[t[0] for t in _FIXTURE_RUNS])
def test_representative_run_has_no_validator_errors(spec_label: str, run: dict):
    """Warnings are permitted; an error-level violation means an over-restrictive structured constraint."""
    errors = [e for e in _validate(run, driver_context=_CTX) if e.level == "error"]
    assert errors == [], (
        f"spec='{spec_label}': expected no validator errors for representative run, "
        f"got:\n" + "\n".join(f"  [{e.source}] {e.field}: {e.message}" for e in errors)
    )


# -------- reactionDiffusionPvjCoupler's graph-aware rPvj requirement --------
#
# reactionDiffusionPvjCoupler uses the graph's non-empty "pvjResistances" list
# when present and never reads rPvj; otherwise it calls dict.get<scalar>("rPvj"),
# a FatalError when absent. The check needs the materialized graph, so it
# runs from case_diagnostics, which reads the case's files.

#: The 11-node graph cardiacFOAM's monodomain1D3D tutorial ships, verbatim.
_NATIVE_GRAPH = (
    Path(__file__).parent / "fixtures" / "tutorials" / "manufacturedSolutions" / "monodomain1D3D"
    / "constant" / "purkinjeGraph.nodes011"
)


def _pvj_diagnostics(case_root):
    from omnidriver.cardiacfoam.validation import case_diagnostics

    return tuple(d for d in case_diagnostics(case_root) if d.code == "missing_rpvj")


def _build_pvj_case(tmp_path, *, coupler="reactionDiffusionPvjCoupler",
                     myocardium_solver="monodomainSolver",
                     conduction_solver="monodomain1DSolver",
                     set_rpvj=False, graph_present=None, graph_has_resistances=False,
                     graph_file_key=True, scheme=None):
    from omnidriver.cardiacfoam.case_builder import build_electro_properties

    prefix = (
        "$ELECTRO_MODEL_COEFFS.conductionNetworkDomains.purkinjeNetwork"
        ".purkinjeGraphModelCoeffs"
    )
    overrides = {
        "$ELECTRO_MODEL_COEFFS.conductionNetworkDomains.purkinjeNetwork"
        ".conductionSystemDomain": "purkinjeGraphModel",
        f"{prefix}.conductionSystemSolver": conduction_solver,
        f"{prefix}.ionicModel": "BuenoOrovio",
        f"{prefix}.vm1DRest": "-0.084",
        f"{prefix}.rootStimulus.node": "0",
        f"{prefix}.rootStimulus.startTime": "0.0",
        f"{prefix}.rootStimulus.duration": "0.0",
        f"{prefix}.rootStimulus.intensity": "0.0",
        f"{prefix}.outputVariables.export": "(activationTime)",
        "$ELECTRO_MODEL_COEFFS.domainCouplings.pvj.conductionNetworkDomain": "purkinjeNetwork",
        "$ELECTRO_MODEL_COEFFS.domainCouplings.pvj.couplingMode": "unidirectional",
        "$ELECTRO_MODEL_COEFFS.domainCouplings.pvj.electroDomainCoupler": coupler,
    }
    if conduction_solver == "eikonalSolver1D":
        overrides[f"{prefix}.purkinjeCV"] = "[0 1 -1 0 0 0 0] 4.2"
    if myocardium_solver == "eikonalSolver":
        overrides["$ELECTRO_MODEL_COEFFS.eikonalAdvectionDiffusionApproach"] = "true"
        overrides["$ELECTRO_MODEL_COEFFS.stimulusLocationMin"] = "(1e6 1e6 1e6)"
        overrides["$ELECTRO_MODEL_COEFFS.stimulusLocationMax"] = "(1e6 1e6 1e6)"
    if graph_file_key:
        overrides[f"{prefix}.graphFile"] = "purkinjeGraph"
    if scheme is not None:
        overrides["$ELECTRO_MODEL_COEFFS.domainCouplings.pvj.pvjCouplingScheme"] = scheme
    if set_rpvj:
        # rPvj lives on the coupler's own block (domainCouplings.<name>.rPvj),
        # not on the network's purkinjeGraphModelCoeffs.
        overrides["$ELECTRO_MODEL_COEFFS.domainCouplings.pvj.rPvj"] = "150.0"

    selectors = {"myocardiumSolver": myocardium_solver}
    if myocardium_solver != "eikonalSolver":
        selectors["ionicModel"] = "BuenoOrovio"
        selectors["tissue"] = "epicardialCells"
    text = build_electro_properties(selectors, overrides=overrides)
    (tmp_path / "constant").mkdir()
    electro_path = tmp_path / "constant" / "electroProperties"
    electro_path.write_text(text)

    if graph_present:
        graph_text = _NATIVE_GRAPH.read_text()
        if graph_has_resistances:
            graph_text += "pvjResistances (150.0 150.0);\n"
        (tmp_path / "constant" / "purkinjeGraph").write_text(graph_text)

    return electro_path


def test_pvj_resistance_silent_when_rpvj_explicitly_set(tmp_path):
    """rPvj supplied directly -- valid regardless of graph/resistance state."""
    electro_path = _build_pvj_case(tmp_path, set_rpvj=True, graph_present=False)
    diagnostics = _pvj_diagnostics(tmp_path)
    assert diagnostics == ()


def test_pvj_resistance_defers_when_graph_not_yet_materialized(tmp_path):
    """cardiacCore generates the graph later, so a missing graph defers rather than errors."""
    electro_path = _build_pvj_case(tmp_path, set_rpvj=False, graph_present=False)
    diagnostics = _pvj_diagnostics(tmp_path)
    assert diagnostics == ()


def test_pvj_resistance_silent_when_graph_provides_terminal_resistances(tmp_path):
    """The graph's pvjResistances take precedence over rPvj, as in reactionDiffusionPvjCoupler::terminalResistances."""
    electro_path = _build_pvj_case(
        tmp_path, set_rpvj=False, graph_present=True, graph_has_resistances=True,
    )
    diagnostics = _pvj_diagnostics(tmp_path)
    assert diagnostics == ()


def test_pvj_resistance_errors_when_graph_materialized_without_resistances_and_no_rpvj(tmp_path):
    """With neither source, reactionDiffusionPvjCoupler's dict.get<scalar>("rPvj") would FatalError."""
    electro_path = _build_pvj_case(
        tmp_path, set_rpvj=False, graph_present=True, graph_has_resistances=False,
    )
    diagnostics = _pvj_diagnostics(tmp_path)
    assert len(diagnostics) == 1
    assert diagnostics[0].level == "error"
    assert "rPvj" in diagnostics[0].message
    assert "purkinjeNetwork" in diagnostics[0].message


def test_pvj_resistance_irrelevant_for_a_different_coupler(tmp_path):
    """eikonalPvjCoupler never reads rPvj, so the check never fires for it."""
    electro_path = _build_pvj_case(
        tmp_path, coupler="eikonalPvjCoupler",
        myocardium_solver="eikonalSolver", conduction_solver="eikonalSolver1D",
        set_rpvj=False, graph_present=False,
    )
    diagnostics = _pvj_diagnostics(tmp_path)
    assert diagnostics == ()


# -------- the graph file a conduction network names --------
#
# conductionGraph::readFromDict and conductionSystemDomain::readGraphFile stop
# the solver on each of these breaks; case_diagnostics names them before it runs.

def _graph_diagnostics(tmp_path, graph_text, **case):
    from omnidriver.cardiacfoam.validation import case_diagnostics

    _build_pvj_case(tmp_path, set_rpvj=True, **case)
    (tmp_path / "constant" / "purkinjeGraph").write_text(graph_text)
    return [
        (item.code, item.field, item.message) for item in case_diagnostics(tmp_path)
        if item.source == "constant/purkinjeGraph"
    ]


def test_the_native_graph_passes(tmp_path):
    assert _graph_diagnostics(tmp_path, _NATIVE_GRAPH.read_text()) == []


@pytest.mark.parametrize("old,new,field,reason", [
    ("(9 10 0.1 1)", "(9 10 0.1)", "conductionEdges", "entry 9 has 3 values"),
    ("(9 10 0.1 1)", "(9 10 0.1 1)\n    (10 0 0.1 1)", "conductionEdges", "11 edges over 11 nodes"),
    ("(4 5 0.1 1)", "(5 5 0.1 1)", "conductionEdges", "node 0 reaches 10 of 11 nodes"),
    ("(4 5 0.1 1)", "(4 1e400 0.1 1)", "conductionEdges", "entry 4 names a node that is no number"),
    ("(4 5 0.1 1)", "(nan 5 0.1 1)", "conductionEdges", "entry 4 names a node that is no number"),
    ("rootNode\n0;", "rootNode\n11;", "rootNode", "rootNode 11 is outside"),
    ("(5 10);", "(5 11);", "pvjNodes", "[11] are outside"),
    ("    (1 0.166666666667 0.333333333333)\n);\n\nconductionEdges", ");\n\nconductionEdges", "pvjLocations", "1 values for 2"),
    ("    (0.9 0.166666666667 0.333333333333)\n", "", "points", "10 positions for 11 nodes"),
])
def test_a_graph_break_the_solver_stops_on_is_named(tmp_path, old, new, field, reason):
    text = _NATIVE_GRAPH.read_text()
    assert old in text
    found = _graph_diagnostics(tmp_path, text.replace(old, new, 1))
    assert [(code, name) for code, name, _ in found] == [("conduction_graph_invalid", field)]
    assert reason in found[0][2]


@pytest.mark.parametrize("resistances,case,refused", [
    ("(150)", {}, True),
    ("(150 150 150)", {}, False),
    ("(150 150 150)", {"scheme": "implicit"}, True),
    ("(150)", {"coupler": "eikonalMonodomainPvjCoupler", "conduction_solver": "restitutionEikonalSolver1D"}, True),
    ("(150 150 150)", {"coupler": "eikonalMonodomainPvjCoupler", "conduction_solver": "restitutionEikonalSolver1D"}, False),
    ("(150)", {"coupler": "eikonalPvjCoupler", "myocardium_solver": "eikonalSolver", "conduction_solver": "eikonalSolver1D"}, False),
])
def test_a_resistance_list_of_the_wrong_length_is_refused_where_a_coupler_reads_past_it(tmp_path, resistances, case, refused):
    text = _NATIVE_GRAPH.read_text() + f"pvjResistances {resistances};\n"
    found = [(code, field) for code, field, _ in _graph_diagnostics(tmp_path, text, **case)]
    assert found == ([("conduction_graph_invalid", "pvjResistances")] if refused else [])


def test_a_graph_without_a_key_the_solver_reads_is_refused(tmp_path):
    text = _NATIVE_GRAPH.read_text().replace("rootNode\n0;\n", "")
    assert _graph_diagnostics(tmp_path, text) == [
        ("catalog_rule", "rootNode", "rootNode is required."),
    ]


def test_a_graph_in_counted_list_form_is_read(tmp_path):
    """1DgraphToFoam writes every list with its element count first."""
    text = _NATIVE_GRAPH.read_text().replace("pvjNodes\n(5 10);", "pvjNodes\n2(5 10);")
    text = text.replace("conductionEdges\n(", "conductionEdges\n10\n(").replace("(0 1 0.1 1)", "4(0 1 0.1 1)")
    assert _graph_diagnostics(tmp_path, text) == []


def test_a_uniform_resistance_list_stands_in_for_rpvj(tmp_path):
    """OpenFOAM's N{value} is a list of N copies, so the coupler has its resistances and never reads rPvj."""
    _build_pvj_case(tmp_path, set_rpvj=False, graph_present=True)
    graph = tmp_path / "constant" / "purkinjeGraph"
    graph.write_text(graph.read_text() + "pvjResistances 2{100};\n")
    assert _pvj_diagnostics(tmp_path) == ()


def test_a_graph_key_omnid_cannot_read_is_left_to_the_solver(tmp_path):
    text = _NATIVE_GRAPH.read_text().replace("(5 10);", "(5 $junction);")
    assert [(code, field) for code, field, _ in _graph_diagnostics(tmp_path, text)] == [
        ("conduction_graph_unjudged", "pvjNodes"),
    ]


def test_a_block_the_case_holds_turns_on_the_rules_gated_on_its_presence():
    from omnidriver.cardiacfoam.record_key_validation import _ELECTRO_ENTRIES_BY_PATH
    from omnidriver.cardiacfoam.validation import infer_virtual_presence

    context = {"myocardiumSolver": "singleCellSolver", "singleCellStimulus.stim_start": 20.0}
    entries = _ELECTRO_ENTRIES_BY_PATH.values()
    without = {item.field for item in rule_diagnostics(entries, dict(context), document="doc")}
    with_presence = dict(context)
    infer_virtual_presence(with_presence)
    gated = {item.field for item in rule_diagnostics(entries, with_presence, document="doc")} - without
    assert gated and all(field.startswith("singleCellStimulus.") for field in gated)


def _external_stimulus_case(tmp_path, stimulus):
    constant = tmp_path / "constant"
    constant.mkdir()
    header = "FoamFile { version 2.0; format ascii; class dictionary; object x; }\n"
    (constant / "electroProperties").write_text(
        header + "myocardiumSolver monodomainSolver;\n"
        "monodomainSolverCoeffs { ionicModel TNNP; externalStimulus { " + stimulus + " } }\n"
    )
    from omnidriver.cardiacfoam.validation import case_diagnostics

    return {item.message for item in case_diagnostics(tmp_path) if item.level == "error"}


def test_an_external_stimulus_needs_each_corner_as_one_value_or_a_list(tmp_path):
    errors = _external_stimulus_case(
        tmp_path, "stimulusLocationMin (0 0 0); stimulusDuration 0.002; stimulusIntensity 50000;"
    )
    assert "one of externalStimulus.stimulusLocationMax, externalStimulus.stimulusLocationMaxList is required." in errors
    assert not any("stimulusDuration" in message or "stimulusIntensity" in message for message in errors)


def test_an_external_stimulus_with_both_corners_breaks_no_rule(tmp_path):
    errors = _external_stimulus_case(
        tmp_path,
        "stimulusLocationMin (0 0 0); stimulusLocationMax (1 1 1); stimulusDuration 0.002; stimulusIntensity 50000;",
    )
    assert not any("stimulus" in message for message in errors)


def test_the_resolved_control_dict_is_judged_beside_electro_properties(tmp_path):
    from omnidriver.cardiacfoam.validation import case_diagnostics

    constant, system = tmp_path / "constant", tmp_path / "system"
    constant.mkdir()
    system.mkdir()
    header = "FoamFile { version 2.0; format ascii; class dictionary; object x; }\n"
    (constant / "electroProperties").write_text(
        header + "myocardiumSolver singleCellSolver;\nsingleCellSolverCoeffs { ionicModel TNNP; }\n"
    )
    (system / "controlDict").write_text(header + "deltaT 0; startFrom startTime; stopAt endTime;\n")
    messages = {item.message for item in case_diagnostics(tmp_path) if item.source == "system/controlDict"}
    assert messages == {
        "deltaT is 0, outside the catalogue's bounds: must be more than 0.",
        "startTime is required when startFrom=startTime.", "endTime is required when stopAt=endTime.",
        "one of writeFrequency, writeInterval is required.",
    }


def test_an_empty_external_stimulus_block_still_needs_its_corners(tmp_path):
    assert "one of externalStimulus.stimulusLocationMin, externalStimulus.stimulusLocationMinList is required." in (
        _external_stimulus_case(tmp_path, "")
    )
