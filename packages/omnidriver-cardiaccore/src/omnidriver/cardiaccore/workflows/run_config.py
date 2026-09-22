"""Construct the cardiacCore preprocessing RunDocument configuration."""

from pathlib import Path
from omnidriver.core.planning_types import diagnostic
from .overrides import qualified_slot_key, read_input_values, validate_input_overrides


def resolve_workflow_inputs(spec):
    """Resolve the effective configuration for a spec, once.

    Returns ``(values, diagnostics)`` keyed by
    :func:`~omnidriver.cardiaccore.workflows.overrides.qualified_slot_key`, so a
    leaf name declared by two documents occupies two slots. Staging, validation,
    the workflow DAG and provenance all read this one answer; resolving twice is
    how a DAG came to declare inputs the case does not read.

    Added 2026-09-22 (audit finding S3).
    """
    active_paths = (spec.metadata or {}).get("active_input_paths")
    paths = None if active_paths is None else tuple(active_paths)
    try:
        values = read_input_values(Path(spec.case_root), paths=paths)
    except (FileNotFoundError, KeyError, ValueError, RuntimeError) as exc:
        return {}, (
            diagnostic(
                "error", "unreadable_preprocessing_input", str(exc),
                source=str(spec.case_root),
            ),
        )
    requested = (spec.metadata or {}).get("input_overrides", {})
    try:
        values.update(validate_input_overrides(requested, allowed_paths=paths))
    except (TypeError, ValueError) as exc:
        return {}, (diagnostic("error", "invalid_input_overrides", str(exc)),)
    # An absent document contributes no slot at all. Recording it as `None`
    # is how an absent scar dictionary came to overwrite a present
    # conductivity dictionary's field name.
    return (
        {
            qualified_slot_key(driver_path): value
            for driver_path, value in values.items()
            if value is not None
        },
        (),
    )


def build_config(spec):
    config = {"preprocessing": {}}
    values, diagnostics = resolve_workflow_inputs(spec)
    if diagnostics:
        return config, diagnostics
    config["preprocessing"] = values
    return config, ()


def _relevant_catalog_paths(spec, plugin) -> tuple[str, ...]:
    """Declared entries whose document the spec's own workflow steps touch.

    Scoping to *every* catalog entry (``paths=None``) is wrong: several
    documents (``setCardiacScarDict``, ``setPurkinjeScarDict``,
    ``coordinatesConventionDict``) are declared-only -- no current tutorial
    runs their utility -- so reading the whole catalog would let a case that
    never runs ``setCardiacScar`` report a value from a scar dictionary that
    does not exist. Scoping to what the spec's own utilities read keeps this
    a per-workflow check, matching what actually gets staged and run.

    **Corrected 2026-09-22:** this also cited a ``slot_key`` collision between
    ``$CARDIAC_SCAR.fiberField`` and ``$CARDIAC_CONDUCTIVITY.fiberField``,
    where iteration order could overwrite a real value with an absent one. That
    collision was real (audit findings S1, S3) and is now fixed at its cause by
    ``qualified_slot_key``, which keeps the scope token. The scoping below is
    kept for the declared-only reason above, which stands on its own.
    """
    from .overrides import resolve_override_target
    from ..catalogs.inputs import CATALOG

    steps = ((spec.metadata or {}).get("workflow_dag") or {}).get("steps") or ()
    manifests = plugin.get_utility_manifests()
    documents = {
        path
        for step in steps
        for path in getattr(manifests.get(step.get("command")), "inputs", ())
        if path.startswith("system/")
    }
    if not documents:
        return ()
    return tuple(
        entry.driver_path for entry in CATALOG.entries
        if resolve_override_target(entry.driver_path).file_relpath in documents
    )


def validate_configuration(spec, plugin):
    """Check the spec's own workflow-relevant catalog entries against the
    resolved case, at plan time.

    ``build_config`` above only reads the tutorial's declared
    ``active_input_paths`` -- for the two Purkinje-tree tutorials that is a
    narrower set than every entry their own workflow steps touch (see
    ``PURKINJE_TREE_INPUT_PATHS`` in ``workflows/preprocessing.py``), so a
    catalog-declared co-requirement outside that set (for example the
    bidomain ``conductivityIntracellular``/``conductivityExtracellular``
    pair in ``catalogs/inputs.py``) goes unchecked until a RunDocument's
    ``config`` happens to expose it at run/step time. This reads those
    entries directly from the resolved case instead -- the same way
    cardiacFoam's own ``validate_configuration`` reads ``electroProperties``
    -- independent of what a given tutorial exposes as overridable, reusing
    the same generic catalog validator (``required``/``co_required_with``/
    ``mutually_exclusive_with``/enum) that ``validate_run`` applies to a
    built RunDocument.

    A generic case-folder run (``spec.metadata["generic_case"]``) has no
    cardiacCore dictionaries at all -- it runs its own declared workflow
    with this plugin merely active, not a cardiacCore preprocessing
    tutorial. ``run_document_adapter._run_document_from_case`` already
    skips ``validate_run`` entirely for that case at run/step time; this
    plan-time check must honour the same bypass; e.g. our own
    test_generic_contract.py::test_controlled_allrun_executes_without_domain_claims
    starts a case_folder entry that supplies none of this catalog.
    """
    if spec.metadata and spec.metadata.get("generic_case"):
        return ()

    relevant_paths = _relevant_catalog_paths(spec, plugin)
    if not relevant_paths:
        return ()

    from types import SimpleNamespace
    from omnidriver.core.plugin_interface import driver_context as _driver_context
    from omnidriver.core.specs.validation import validate_run
    from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin

    case_root = Path(spec.case_root)
    try:
        values = read_input_values(case_root, paths=relevant_paths)
    except (FileNotFoundError, KeyError, ValueError, RuntimeError):
        # build_config raises its own diagnostic for an unreadable case;
        # this hook does not need to duplicate it.
        return ()

    fake_run = SimpleNamespace(config={"preprocessing": {
        qualified_slot_key(driver_path): value
        for driver_path, value in values.items()
        if value is not None
    }})
    # `validate_run` already returns the canonical `StrictDiagnostic` shape
    # (core.planning_types, code="run_validation", source=<phase>) as of
    # Phase 0 Task 10 -- passed through unchanged rather than re-wrapped
    # field-for-field through a now-deleted `ValidationError.phase`.
    #
    # Corrected 2026-09-22 (audit finding S2, wiring this hook): a bare
    # `_driver_context(plugin, ...)` raises, because `plugin` declares
    # `requires: [org.omnidriver.openfoam.environment]` (plugin.yaml) and
    # `provider_stack.order_providers` (audit finding C1) now refuses an
    # unmet requirement rather than silently ordering a partial stack. Every
    # other caller in this package composes the environment adapter
    # alongside `CardiacCorePlugin` for exactly this reason (see
    # tests/test_apply_works_through_the_stack.py's
    # `cardiaccore_stack_context` fixture) -- this hook was the one caller
    # that did not, because until this commit it had never actually run.
    return validate_run(
        fake_run,
        driver_context=_driver_context(
            OpenFOAMEnvironmentPlugin(), plugin,
            source="cardiaccore.validate_configuration",
        ),
    )
