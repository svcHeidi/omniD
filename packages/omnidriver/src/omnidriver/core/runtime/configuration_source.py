"""One rule for what a RunDocument's ``configurationSource`` implies.

Step 4c (docs/superpowers/specs/2026-09-24-tutorials-are-pointers-design.md)
closes a defect recorded at the end of step 4b: planning
(``run_document_adapter``) decided whether to validate a document's
``config`` by inferring "generic case" from ``spec.metadata`` -- a marker
execution (``run_document_exec``) cannot see, because a ``RunDocument`` never
carried it forward. Execution therefore validated an intentionally-empty
generic-case/tutorial-record config against the plugin's schema unconditionally,
and refused every such run.

The fix is explicit, not inferred, and shared: ``configurationSource`` is a
required field the document itself states (schemas/run-document.json), and
this module is the ONE function both producers call to turn that source into
"which validations apply". Neither ``run_document_adapter`` nor
``run_document_exec`` may re-derive this decision independently.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..planning_types import StrictDiagnostic, diagnostic

#: The only two values schemas/run-document.json's "configurationSource"
#: enum accepts. Kept here (not just in the schema) so this module's own
#: "unknown source" branch below can name them in its message without
#: importing the schema JSON.
CONFIGURATION_SOURCES: tuple[str, ...] = ("document", "case")


@dataclass(frozen=True)
class ConfigurationSourceDecision:
    """What ``configuration_source`` means for validating a document's config.

    ``validate_document_config``: whether ``validate_run`` (dictionary/
    semantic checks) and the plugin's declared JSON Schema apply to
    ``config``. True for "document" (config carries the configuration);
    false for "case" (the case files already do, so there is nothing in
    ``config`` to check) and false for an unrecognized source (nothing is
    trustworthy enough to validate).

    ``diagnostics``: structural refusals found by this decision alone --
    a "case" source whose ``config`` is not empty (a contradiction: two
    sources claiming to own one fact), or a source outside
    ``CONFIGURATION_SOURCES``. Always in addition to, never instead of,
    whatever ``validate_run``/the schema check would separately find.
    """

    validate_document_config: bool
    diagnostics: tuple[StrictDiagnostic, ...] = ()


def _config_carries_values(value: Any) -> bool:
    """True if ``value`` holds a real configuration value anywhere inside it.

    A "case"-sourced document's ``config`` must be empty, but "empty" is a
    structural claim, not ``config == {}``: a plugin's own config builder
    (e.g. cardiacFoam's ``build_config``) represents "nothing to configure"
    as a shell of empty phase dicts (``{"anatomy": {}, "physics": {}, ...}``),
    which is truthy but carries no value. Recurses through mappings and
    sequences; ``None`` and empty containers are not "values", anything else
    (a string, number, bool, or a non-empty container containing one) is.
    """
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
    """The one decision both planning and execution consult.

    Called by ``run_document_adapter._run_document_from_case`` (planning, on
    the config it just built) and ``run_document_exec.build_execution_inputs``
    (execution, on an ingested document's config) -- see each module's own
    call site for how the resulting diagnostics and
    ``validate_document_config`` flag are used.
    """
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
