"""Required-field enforcement for every configured dynamic block. The generic pass
skips ``dynamic_path`` entries, and ``domainCouplings.<name>`` leaves have no
``typical_value``, so a configured block can reach the solver missing a key.
"""

from __future__ import annotations

from omnidriver.cardiacfoam.validation import (
    _evaluate_dynamic_required_fields,
)


def _fields(errors) -> list[str]:
    return sorted(e.field for e in errors)


def test_configured_domain_coupling_missing_required_leaf_is_reported():
    context = {
        "myocardiumSolver": "monodomainSolver",
        "domainCouplings.couplingA.electroDomainCoupler": "eikonalMonodomainPvjCoupler",
    }
    fields = _fields(_evaluate_dynamic_required_fields(context))
    assert "domainCouplings.couplingA.conductionNetworkDomain" in fields
    assert "domainCouplings.couplingA.couplingMode" in fields


def test_a_complete_domain_coupling_is_silent():
    context = {
        "myocardiumSolver": "monodomainSolver",
        "domainCouplings.couplingA.electroDomainCoupler": "monodomainPvjCoupler",
        "domainCouplings.couplingA.conductionNetworkDomain": "purkinjeNetwork",
        "domainCouplings.couplingA.couplingMode": "twoWay",
    }
    assert _evaluate_dynamic_required_fields(context) == []


def test_an_undeclared_block_is_not_invented():
    assert _evaluate_dynamic_required_fields({"myocardiumSolver": "monodomainSolver"}) == []


def test_sibling_instances_are_scoped_independently():
    """One coupling's value must never satisfy another's requirement."""
    context = {
        "myocardiumSolver": "monodomainSolver",
        "domainCouplings.couplingA.electroDomainCoupler": "monodomainPvjCoupler",
        "domainCouplings.couplingA.conductionNetworkDomain": "netA",
        "domainCouplings.couplingA.couplingMode": "twoWay",
        "domainCouplings.couplingB.electroDomainCoupler": "monodomainPvjCoupler",
    }
    fields = _fields(_evaluate_dynamic_required_fields(context))
    assert all(f.startswith("domainCouplings.couplingB.") for f in fields), fields
    assert "domainCouplings.couplingB.couplingMode" in fields


def test_conduction_network_enforcement_is_preserved():
    context = {
        "myocardiumSolver": "monodomainSolver",
        "conductionNetworkDomains.netA.conductionSystemDomain": "purkinjeGraphModel",
    }
    fields = _fields(_evaluate_dynamic_required_fields(context))
    assert all(f.startswith("conductionNetworkDomains.netA.") for f in fields), fields
