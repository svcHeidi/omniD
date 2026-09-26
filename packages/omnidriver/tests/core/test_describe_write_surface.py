"""`describe`'s write surface (Phase 2 Task 13,
docs/superpowers/plans/2026-09-20-phase2-one-write-channel.md).

The plan's own sketched test imports `CATALOG.entries` directly -- cardiac
vocabulary a core test must not import. Corrected 2026-09-23: this uses a
fake plugin double (the same pattern `test_case_writer_capability.py`
already uses via `plugin_capabilities.adapt_plugin_capabilities`), not a
real adapter's catalog.
"""
from __future__ import annotations

from dataclasses import dataclass

from omnidriver.core import plugin_capabilities
from omnidriver.core.case_write import CaseWriteRecord, MUTATION_MODES, VALUE_SOURCES
from omnidriver.core.contracts.dictionary import DictEntry
from omnidriver.core.introspection import _resolve_proposed_changes, _write_surface
from omnidriver.core.runtime.models import CaseConfig, TutorialSpec


@dataclass
class _FakeDriverContext:
    capabilities: "plugin_capabilities.PluginCapabilities"


def _spec(metadata: dict | None = None) -> TutorialSpec:
    return TutorialSpec(
        name="fake",
        case_root=__import__("pathlib").Path("/tmp/fake-case-root-not-touched"),
        setup_root=__import__("pathlib").Path("/tmp/fake-setup-root-not-touched"),
        output_dir=__import__("pathlib").Path("/tmp/fake-output-dir-not-touched"),
        build_cases=lambda: [CaseConfig(case_id="only", params={})],
        apply_case=lambda case_root, case: None,
        metadata=metadata or {},
    )


_ENTRIES = (
    DictEntry(
        driver_path="$FAKE.ionicModel", description="fake", value_kind="word",
        typical_value="TT06",
    ),
    DictEntry(
        driver_path="$FAKE.deltaT", description="fake", value_kind="scalar",
    ),
)


class _PluginNoWriter:
    plugin_id = "org.fake.no_writer"

    def get_dict_entries(self):
        return _ENTRIES


class _PluginWithWriter(_PluginNoWriter):
    plugin_id = "org.fake.with_writer"

    def resolve_case_mutation(self, request, *, driver_context):
        raise NotImplementedError

    def get_supported_mutation_modes(self):
        return frozenset({"clone_and_patch"})


def _context(plugin) -> _FakeDriverContext:
    return _FakeDriverContext(capabilities=plugin_capabilities.adapt_plugin_capabilities(plugin))


def test_the_described_surface_comes_from_the_validation_contracts():
    """Not a parallel description. The same catalog entries that validate a
    value are the ones described, so the two cannot drift."""
    context = _context(_PluginNoWriter())
    described = _write_surface(driver_context=context, spec=_spec(), overrides=None)
    from_catalog = {entry.driver_path for entry in _ENTRIES}
    assert {item["qualified_id"] for item in described["mutable"]} <= from_catalog
    assert {item["qualified_id"] for item in described["mutable"]} == from_catalog


def test_an_unsupported_mode_is_described_as_unsupported_not_omitted():
    """Omission reads as "no opinion". An agent needs to know the difference
    between a mode that is unsupported and one nobody mentioned."""
    context = _context(_PluginNoWriter())
    described = _write_surface(driver_context=context, spec=_spec(), overrides=None)
    assert set(described["modes"]) == MUTATION_MODES
    for mode, info in described["modes"].items():
        assert info["supported"] is False
        assert info["reason"]


def test_a_supported_mode_is_described_as_supported_with_no_reason_required():
    context = _context(_PluginWithWriter())
    described = _write_surface(driver_context=context, spec=_spec(), overrides=None)
    assert described["modes"]["clone_and_patch"]["supported"] is True
    assert described["modes"]["clone_and_patch"]["reason"] == ""
    assert described["modes"]["synthesize"]["supported"] is False
    assert described["modes"]["synthesize"]["reason"]


def test_every_described_value_carries_its_source():
    context = _context(_PluginNoWriter())
    described = _write_surface(
        driver_context=context, spec=_spec(), overrides={"$FAKE.deltaT": 1e-4},
    )
    for item in described["mutable"]:
        assert item["source"] in VALUE_SOURCES
    by_id = {item["qualified_id"]: item for item in described["mutable"]}
    # Overridden -> "case"; declares a typical_value and was not overridden
    # -> "template"; neither -> "call_site_default".
    assert by_id["$FAKE.deltaT"]["source"] == "case"
    assert by_id["$FAKE.ionicModel"]["source"] == "template"


def test_proposed_changes_lists_what_the_caller_actually_asked_to_change():
    context = _context(_PluginNoWriter())
    described = _write_surface(
        driver_context=context, spec=_spec(), overrides={"$FAKE.deltaT": 1e-4},
    )
    assert [item["qualified_id"] for item in described["proposed_changes"]] == ["$FAKE.deltaT"]
    assert described["proposed_changes"][0]["source"] == "case"


def test_consumed_reuses_the_specs_own_declared_workflow_dag():
    metadata = {
        "workflow_dag": {
            "steps": [
                {"id": "a", "consumes": ["system/aDict", "0/Field"]},
                {"id": "b", "consumes": ["0/Field"]},
            ],
        },
    }
    context = _context(_PluginNoWriter())
    described = _write_surface(driver_context=context, spec=_spec(metadata), overrides=None)
    assert described["consumed"] == ["0/Field", "system/aDict"]


def test_consumed_is_empty_for_a_spec_with_no_workflow_dag():
    context = _context(_PluginNoWriter())
    described = _write_surface(driver_context=context, spec=_spec(), overrides=None)
    assert described["consumed"] == []


def test_a_spec_with_no_plan_case_falls_back_with_a_stated_reason():
    """Phase 3 Task 9: `_resolve_proposed_changes` requires `spec.plan_case`
    to reuse the real resolver; this fake spec (like every fake spec in this
    core-only test module) supplies only `apply_case`. The naive key-match
    fallback must still run -- and say why it, not the richer path,
    produced the result -- rather than going silently empty."""
    context = _context(_PluginNoWriter())
    described = _write_surface(
        driver_context=context, spec=_spec(), overrides={"$FAKE.deltaT": 1e-4},
    )
    assert described["proposed_changes_source"] == "supplied_qualified_ids_only"
    assert "no plan_case" in described["proposed_changes_reason"]
    assert described["expected_effects"] == []
    # The fallback path's own items are enriched with an explicit "operation"
    # (Task 9) -- previously absent, since a flat qualified-id match can only
    # ever represent a "set".
    assert described["proposed_changes"][0]["operation"] == "set"


def _spec_with_plan_case(plan_case, *, case_root=None):
    return TutorialSpec(
        name="fake-with-plan-case",
        case_root=case_root or __import__("pathlib").Path(
            "/tmp/fake-plan-case-root-does-not-exist",
        ),
        setup_root=__import__("pathlib").Path("/tmp/fake-setup-root-not-touched"),
        output_dir=__import__("pathlib").Path("/tmp/fake-output-dir-not-touched"),
        build_cases=lambda: [CaseConfig(case_id="only", params={})],
        plan_case=plan_case,
    )


def test_a_sweep_that_has_not_collapsed_to_one_case_reports_a_reason():
    def _build_cases():
        return [
            CaseConfig(case_id="a", params={}),
            CaseConfig(case_id="b", params={}),
        ]

    spec = TutorialSpec(
        name="fake-multi-case",
        case_root=__import__("pathlib").Path("/tmp/fake-plan-case-root-does-not-exist"),
        setup_root=__import__("pathlib").Path("/tmp/fake-setup-root-not-touched"),
        output_dir=__import__("pathlib").Path("/tmp/fake-output-dir-not-touched"),
        build_cases=_build_cases,
        plan_case=lambda case_root, case: None,
    )
    context = _context(_PluginNoWriter())
    proposed, effects, reason = _resolve_proposed_changes(driver_context=context, spec=spec)
    assert proposed is None
    assert effects == ()
    assert "resolved to 2 cases" in reason


def test_a_staged_plan_case_that_raises_reports_a_reason_not_a_crash():
    def _plan_case(case_root, case):
        raise ValueError("this tutorial's own resolution refused something")

    spec = _spec_with_plan_case(_plan_case)
    context = _context(_PluginNoWriter())
    proposed, effects, reason = _resolve_proposed_changes(driver_context=context, spec=spec)
    assert proposed is None
    assert effects == ()
    assert "this tutorial's own resolution refused something" in reason


def test_a_plan_case_no_op_is_an_empty_list_not_a_reason():
    """`plan_case` returning `None` is the documented no-op contract
    (`commit_case_overrides`'s own docstring) -- a legitimate, different
    answer from "could not be determined"."""
    spec = _spec_with_plan_case(lambda case_root, case: None)
    context = _context(_PluginNoWriter())
    proposed, effects, reason = _resolve_proposed_changes(driver_context=context, spec=spec)
    assert proposed == []
    assert effects == ()
    assert reason == ""


def test_a_real_case_write_record_is_read_into_proposed_changes():
    def _plan_case(case_root, case):
        return CaseWriteRecord(
            transaction_id="t", plan_id="p", plan_digest="d",
            committed=(), evidence=(), status="committed",
            parameters=(
                {
                    "qualified_id": "$FAKE.deltaT", "document": "system/controlDict",
                    "value": 1e-4, "source": "case", "operation": "set",
                },
            ),
            expected_effects=("set '$FAKE.deltaT' in system/controlDict",),
        )

    spec = _spec_with_plan_case(_plan_case)
    context = _context(_PluginNoWriter())
    proposed, effects, reason = _resolve_proposed_changes(driver_context=context, spec=spec)
    assert reason == ""
    assert proposed == [
        {
            "qualified_id": "$FAKE.deltaT", "document": "system/controlDict",
            "value": 1e-4, "source": "case", "operation": "set",
        },
    ]
    assert effects == ("set '$FAKE.deltaT' in system/controlDict",)


def test_a_nested_parameter_value_reaches_describe_as_plain_json(tmp_path, monkeypatch):
    """Found 2026-09-24: `describe --entry cable1DCVConvergence` exited 1 with
    ``Object of type mappingproxy is not JSON serializable`` at the CLI's
    ``json.dumps(describe_entry(...))``. `CaseWriteRecord.__post_init__`
    deep-freezes ``parameters`` (`_freeze`), so a nested value -- a dimensioned
    tensor, ``{"dimensions": ..., "value": ...}`` -- is a `MappingProxyType`
    of tuples on the record; `_resolve_proposed_changes` read
    ``record.parameters`` directly instead of ``record.to_json()``, the form
    that undoes the freeze. A scalar value (the test above) cannot see this.

    Runs the real public edge -- `describe_entry` then `json.dumps`, exactly
    the CLI's call -- under a `MinimalTestPlugin` whose tutorial catalog
    supplies the spec, so nothing here is cardiac.
    """
    from pathlib import Path
    import json

    from omnidriver.core.introspection import describe_entry
    from omnidriver.core.plugin_interface import driver_context
    from plugins.minimal_plugin import MinimalTestPlugin

    monkeypatch.setenv("SKIP_ENV_DIAGNOSTICS", "1")
    monkeypatch.setenv("SKIP_GEOMETRY_DIAGNOSTICS", "1")
    nested_value = {"dimensions": [0, 1, -1], "value": [1.5, 0.0, 2.5]}

    def _plan_case(case_root, case):
        return CaseWriteRecord(
            transaction_id="t", plan_id="p", plan_digest="d",
            committed=(), evidence=(), status="committed",
            parameters=(
                {
                    "qualified_id": "$GENERIC.tensor", "document": "system/generic",
                    "value": nested_value, "source": "case", "operation": "set",
                },
            ),
            expected_effects=("set '$GENERIC.tensor' in system/generic",),
        )

    def _make_spec(*, cases_root: str | Path) -> TutorialSpec:
        return TutorialSpec(
            name="nestedValue",
            case_root=Path(cases_root) / "nestedValue",
            setup_root=Path(cases_root) / "nestedValue",
            output_dir=Path(cases_root) / "outputs",
            build_cases=lambda: [CaseConfig(case_id="only", params={})],
            plan_case=_plan_case,
        )

    class _NestedValuePlugin(MinimalTestPlugin):
        def get_tutorial_catalog(self):
            return {
                "registered_tutorials": ("nestedValue",),
                "spec_factories": {"nestedValue": _make_spec},
            }

    payload = describe_entry(
        "nestedValue",
        overrides={"cases_root": str(tmp_path)},
        driver_context=driver_context(_NestedValuePlugin(), source="test"),
    )
    surface = json.loads(json.dumps(payload))["write_surface"]
    assert surface["proposed_changes_reason"] == ""
    assert surface["proposed_changes"] == [
        {
            "qualified_id": "$GENERIC.tensor", "document": "system/generic",
            "value": nested_value, "source": "case", "operation": "set",
        },
    ]
