"""The solver conformance suite: an executable definition of "a solver can plug into omniD".

Shipped in the core wheel so a solver's authors can run it against their own plugin (``omnidriver check``)."""
from omnidriver.core.conformance_study import ConformanceStudy, QuantityTarget, RankEvidence

from .checks import CHECKS, run_check
from .target import CheckVerdict, ConformanceTarget

__all__ = ["CHECKS", "CheckVerdict", "ConformanceStudy", "ConformanceTarget", "QuantityTarget", "RankEvidence", "run_check"]
