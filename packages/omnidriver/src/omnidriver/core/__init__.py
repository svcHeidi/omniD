"""Core shared modules for the omnidriver orchestrator.

Deliberately no eager re-exports here: ``core.introspection`` transitively
imports ``core.strict_planning``, which imports ``omnidriver.openfoam`` for
environment preflight checks. Re-exporting from this ``__init__.py`` would
run that chain the moment anything imports a single ``omnidriver.core.*``
submodule, creating a circular import the instant ``omnidriver.openfoam``
itself needs any ``omnidriver.core`` symbol (as it does, e.g. for
``StrictDiagnostic``). Import submodules directly: ``from
omnidriver.core.introspection import describe_tutorial``, not ``from
omnidriver.core import describe_tutorial``.
"""
