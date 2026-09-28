"""One rule for what a RunDocument's ``configurationSource`` implies.

Both producers (``run_document_adapter``, ``run_document_exec``) must call
this rather than re-deriving the decision independently; see
``docs/superpowers/specs/2026-09-24-tutorials-are-pointers-design.md``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..planning_types import StrictDiagnostic, diagnostic

#: The two values schemas/run-document.json's "configurationSource" enum
#: accepts, named here so the "unknown source" message below can cite them
#: without importing the schema JSON.
CONFIGURATION_SOURCES: tuple[str, ...] = ("document", "case")


@dataclass(frozen=True)
class ConfigurationSourceDecision:
    """What ``configuration_source`` means for validating a document's config.

    ``validate_document_config`` is true only for a "document" source.
    ``diagnostics`` are structural refusals found by this decision alone
    (e.g. a "case" source whose ``config`` is not empty), always additional
    to whatever ``validate_run``/the schema check separately finds.
    """

    validate_document_config: bool
    diagnostics: tuple[StrictDiagnostic, ...] = ()


def _config_carries_values(value: Any) -> bool:
    """True if ``value`` holds a real configuration value anywhere inside it; a shell of empty phase dicts does not count."""
    if value is None:
        return False
    if isinstance(value, Mapping):
        return any(_config_carries_values(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(_config_carries_values(v) for v in value)
    return True


def resolve_configuration_source(
    configuration_source: Any, config: Mapping[str, Any],
) -> ConfigurationSourceDecision:
    """The one decision both planning (``run_document_adapter``) and execution (``run_document_exec``) consult."""
    if configuration_source == "case":
        if _config_carries_values(config):
            return ConfigurationSourceDecision(
                validate_document_config=False,
                diagnostics=(diagnostic(
                    "error",
                    "case_configuration_source_carries_config",
                    "RunDocument.configurationSource is 'case' (the case "
                    "files hold the configuration) but config is not empty. "
                    "A case-sourced document must not also carry document "
                    "config -- this is a contradiction between two claimed "
                    "sources for the same fact, not a value to merge or "
                    "prefer, and it is refused rather than silently ignored "
                    "(an agent-authored document claiming 'case' is exactly "
                    "how unvalidated config would otherwise be smuggled past "
                    "the plugin schema check).",
                    field="config",
                ),),
            )
        return ConfigurationSourceDecision(validate_document_config=False)
    if configuration_source == "document":
        return ConfigurationSourceDecision(validate_document_config=True)
    return ConfigurationSourceDecision(
        validate_document_config=False,
        diagnostics=(diagnostic(
            "error",
            "unknown_configuration_source",
            "RunDocument.configurationSource must be one of "
            f"{CONFIGURATION_SOURCES!r}, got {configuration_source!r}.",
            field="configurationSource",
        ),),
    )
