"""Curated registry of the canonical regression-equivalence cases.

Owned by omnidriver, not derived from every upstream ``regression/*.reference``,
so upstream can add tutorials without breaking this suite.
"""
from __future__ import annotations

from dataclasses import dataclass
@dataclass(frozen=True)
class RegressionCase:
    # Path under tutorials/, matching an Alltest-regression REGRESSION_TESTS entry.
    case_dir: str
    # Registered agent entry name, or None for cases with no agent spec.
    entry_name: str | None
    # Case-authored dicts the agent regenerates, for the round-trip check.
    dicts: tuple[str, ...]
    # Representative reference-comparison file, relative to the case dir.
    reference_file: str
    regression_script: str = "regression/regressionTest.sh"
    # False for layouts case discovery does not recognize (e.g. electromechanical
    # cases keep electroProperties at constant/electro/).
    generic_addressable: bool = True
    # Expected `resolve_strict` resolution (`runtime.registry.classify_entry`
    # vocabulary): "registered" or "tutorial_record".
    resolution: str = "registered"

    @property
    def mapped(self) -> bool:
        return self.entry_name is not None

    @property
    def drivers(self) -> tuple[str, ...]:
        # Mapped cases are driven both ways to confirm the agent can reason
        # about them through the strict entry and the generic case-folder path.
        return ("strict", "generic") if self.mapped else ("generic",)


_ELECTRO = "constant/electroProperties"
_PHYSICS = "constant/physicsProperties"


_KNOWN_CASES: tuple[RegressionCase, ...] = (
    RegressionCase(
        "electrophysiologyProtocols/singleCell", "singleCell",
        (_ELECTRO, _PHYSICS), "regression/singleCell.reference",
        resolution="tutorial_record",
    ),
    RegressionCase(
        "NiedererEtAl2011verification", "niederer2011",
        (_ELECTRO, _PHYSICS), "regression/NiedererEtAl2011.reference",
        resolution="tutorial_record",
    ),
    RegressionCase(
        "manufacturedSolutions/bidomain", "manufacturedBidomain",
        (_ELECTRO, _PHYSICS), "regression/bidomainManufactured.reference",
        resolution="tutorial_record",
    ),
    RegressionCase(
        "manufacturedSolutions/monodomainPseudoECG", "manufacturedMonodomainPseudoECG",
        (_ELECTRO, _PHYSICS), "regression/monodomainPseudoECG.reference",
        resolution="tutorial_record",
    ),
    RegressionCase(
        "manufacturedSolutions/eikonalECG", "manufacturedEikonalECG",
        (_ELECTRO, _PHYSICS), "regression/eikonalECG.reference",
        resolution="tutorial_record",
    ),
    RegressionCase(
        "manufacturedSolutions/bathBidomain", "manufacturedBathBidomain",
        (_ELECTRO, _PHYSICS), "regression/bathBidomainManufactured.reference",
        resolution="tutorial_record",
    ),
    # electromechanicsProtocols/springSupportedSlab is deliberately not registered.
    RegressionCase(
        "electrophysiologyProtocols/rotorInstability", None,
        (), "regression/rotorInstability.reference",
    ),
)
REGRESSION_CASES: tuple[RegressionCase, ...] = _KNOWN_CASES
