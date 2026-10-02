"""Core's own run records come from ``CORE_RUNTIME_RECORDS`` only; a layer above core never restates them."""
from __future__ import annotations

from omnidriver.core.plugin_discovery import load_discovered_plugin
from omnidriver.core.runtime_records import CORE_RUNTIME_RECORDS, case_runtime_conventions


def test_no_provider_declares_cores_own_files() -> None:
    core_names = set(CORE_RUNTIME_RECORDS.generated_file_names) | set(CORE_RUNTIME_RECORDS.generated_directory_names)
    ctx = load_discovered_plugin("openfoam-environment")
    for provider in ctx.providers:
        conventions = provider.get_case_runtime_conventions()
        declared = (
            set(conventions.generated_file_names)
            | set(conventions.generated_directory_names)
            | set(conventions.generated_case_markers)
        )
        assert not declared & core_names, f"{provider.plugin_id} declares core's {sorted(declared & core_names)}"
    merged = case_runtime_conventions(ctx)
    assert core_names <= set(merged.generated_file_names) | set(merged.generated_directory_names)
