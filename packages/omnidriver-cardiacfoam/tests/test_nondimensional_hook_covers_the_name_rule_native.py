"""Every case the name rule ("manufactured"/"verification" in the entry name or workflow family)
exempts from mesh-scale checks is exempted by the plugin's ``is_nondimensional_case`` hook, which
reads the case's files. Runs against the native tree supplied through OMNIDRIVER_NATIVE_TUTORIALS."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from omnidriver.core.plugin_discovery import load_discovered_plugin
from omnidriver.core.runtime.record_execution import record_case_spec

pytestmark = pytest.mark.native


def _native_tutorials_root() -> Path:
    value = os.environ.get("OMNIDRIVER_NATIVE_TUTORIALS")
    if not value:
        pytest.fail(
            "OMNIDRIVER_NATIVE_TUTORIALS is not set. A test marked "
            "@pytest.mark.native needs the native cardiacFOAM tutorials tree "
            "supplied explicitly, e.g. OMNIDRIVER_NATIVE_TUTORIALS="
            "/Users/simaocastro/noFrontendCardiacFoam_minor_errors/tutorials"
        )
    return Path(value)


def _name_rule(spec) -> bool:
    """The name rule, verbatim: whatever it exempts, the hook must exempt."""
    metadata = spec.metadata or {}
    haystack = (
        f"{metadata.get('entry_name', '') or ''} "
        f"{metadata.get('workflow_family', '') or ''}"
    ).lower()
    return "manufactured" in haystack or "verification" in haystack


def test_every_case_the_name_rule_exempted_is_exempted_by_the_hook():
    root = _native_tutorials_root()
    ctx = load_discovered_plugin("cardiacfoam")
    specs = [
        record_case_spec(
            record, case_id=name, staged_case_root=root / record.native_case_relpath,
            workflow_step_ids=(), command_arguments={},
        )
        for name, record in (ctx.capabilities.tutorial_records.catalog() or {}).items()
    ]
    exempted_by_name = [spec for spec in specs if _name_rule(spec)]
    assert exempted_by_name, "the name rule exempted nothing here, so this proves nothing"
    missed = sorted(
        spec.metadata["entry_name"] for spec in exempted_by_name
        if not ctx.capabilities.mesh_diagnostic_policy.is_nondimensional(spec)
    )
    assert missed == [], f"the plugin hook does not exempt {missed}, which the name rule did"
