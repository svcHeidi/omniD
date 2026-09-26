"""Every case the old name rule exempted is exempted by the plugin hook.

spec 2026-09-26-core-generality-design.md §2, A7.
``strict_planning._is_nondimensional_entry`` exempted a case from
mesh-scale checks when its entry name or workflow family contained
"manufactured" or "verification". That rule is deleted. This proves that
the plugin's own hook (``planning_policy.is_nondimensional_case``, which
reads the case's files) exempts every case the rule did. It runs against
the real native tree, supplied only through OMNIDRIVER_NATIVE_TUTORIALS
and never discovered.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from omnidriver.core.plugin_discovery import load_discovered_plugin
from omnidriver.core.runtime.record_execution import record_case_spec
from omnidriver.core.runtime.registry import list_tutorials, load_entry_spec

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
    """The deleted rule, verbatim: whatever it exempted, the hook must exempt."""
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
        load_entry_spec(name, overrides={"cases_root": str(root)}, driver_context=ctx)
        for name in list_tutorials(ctx)
    ]
    specs += [
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
