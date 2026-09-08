"""Skip fixture-dependent tests at their module or function boundary.

The dual-run unit helpers and registry metadata checks need neither a solver
nor the cardiacFoam tutorial tree. Tests reading real tutorial files retain
their explicit ``skip_without_monorepo`` markers. A ``pytestmark`` in conftest
does not propagate to test modules and must not be relied upon as a gate.
"""
