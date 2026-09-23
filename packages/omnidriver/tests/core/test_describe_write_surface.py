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
from omnidriver.core.case_write import MUTATION_MODES, VALUE_SOURCES
from omnidriver.core.contracts.dictionary import DictEntry
from omnidriver.core.introspection import _write_surface
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
