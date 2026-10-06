"""Required-field enforcement for every configured dynamic block: a configured
``domainCouplings.<name>`` block can otherwise reach the solver missing a key."""

from __future__ import annotations

from omnidriver.cardiacfoam.record_key_validation import _ELECTRO_ENTRIES_BY_PATH
from omnidriver.openfoam.case_rules import rule_diagnostics


def _evaluate_dynamic_required_fields(context):
    """The violations inside a block (a partial context also lacks static required keys, which these tests are not about)."""
    found = rule_diagnostics(_ELECTRO_ENTRIES_BY_PATH.values(), context, document="constant/electroProperties")
    return [item for item in found if "." in item.field]


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
        "domainCouplings.couplingA.electroDomainCoupler": "reactionDiffusionPvjCoupler",
        "domainCouplings.couplingA.conductionNetworkDomain": "purkinjeNetwork",
        "domainCouplings.couplingA.couplingMode": "bidirectional",
    }
    assert _evaluate_dynamic_required_fields(context) == []


def test_an_undeclared_block_is_not_invented():
    assert _evaluate_dynamic_required_fields({"myocardiumSolver": "monodomainSolver"}) == []


def test_sibling_instances_are_scoped_independently():
    """One coupling's value must never satisfy another's requirement."""
    context = {
        "myocardiumSolver": "monodomainSolver",
        "domainCouplings.couplingA.electroDomainCoupler": "reactionDiffusionPvjCoupler",
        "domainCouplings.couplingA.conductionNetworkDomain": "netA",
        "domainCouplings.couplingA.couplingMode": "bidirectional",
        "domainCouplings.couplingB.electroDomainCoupler": "reactionDiffusionPvjCoupler",
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


_NETWORK = "conductionNetworkDomains.net.purkinjeGraphModelCoeffs."
_RADIUS = _NETWORK + "purkinjeFibreRadius"


def _bidirectional_context(mode, **extra):
    return {
        "myocardiumSolver": "monodomainSolver",
        "conductionNetworkDomains.net.conductionSystemDomain": "purkinjeGraphModel",
        _NETWORK + "conductionSystemSolver": "monodomain1DSolver",
        "domainCouplings.pvj.electroDomainCoupler": "reactionDiffusionPvjCoupler",
        "domainCouplings.pvj.conductionNetworkDomain": "net",
        "domainCouplings.pvj.couplingMode": mode,
        **extra,
    }


def test_the_fibre_radius_is_required_once_a_coupling_is_bidirectional():
    assert _RADIUS in _fields(_evaluate_dynamic_required_fields(_bidirectional_context("bidirectional")))
    assert _RADIUS not in _fields(_evaluate_dynamic_required_fields(_bidirectional_context("unidirectional")))
    assert _RADIUS not in _fields(_evaluate_dynamic_required_fields(
        _bidirectional_context("bidirectional", **{_RADIUS: 1.7e-5})
    ))


def test_the_fibre_radius_must_be_above_zero():
    found = rule_diagnostics(
        _ELECTRO_ENTRIES_BY_PATH.values(), _bidirectional_context("bidirectional", **{_RADIUS: 0.0}),
        document="constant/electroProperties",
    )
    assert any(item.field == _RADIUS for item in found)
