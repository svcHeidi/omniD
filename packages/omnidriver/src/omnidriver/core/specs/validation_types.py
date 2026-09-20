"""Retired 2026-09-20 (Phase 0 Task 10): this module used to declare
``ValidationError``, a four-field diagnostic shape (``phase``, ``field``,
``message``, ``level``) distinct from -- and missing a ``code`` compared to
-- the canonical ``core.planning_types.StrictDiagnostic`` (``level``,
``code``, ``message``, ``source``, ``field``). ``specs.validation.validate_run``
now returns ``StrictDiagnostic`` directly; every former ``ValidationError``
construction site maps ``phase`` to ``source``. See
``docs/superpowers/plans/2026-09-20-phase0-contract-coherence.md`` Task 10.
"""
