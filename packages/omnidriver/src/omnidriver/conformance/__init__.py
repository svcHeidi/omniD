"""The solver conformance suite: an executable definition of "a solver can
plug into omniD". Design: docs/superpowers/specs/2026-09-25-solver-
conformance-and-opencarp-design.md §4. Shipped in the core wheel so a
third-party solver's authors can run it against their own plugin
(``omnidriver check``)."""
from omnidriver.core.conformance_study import ConformanceStudy, QuantityTarget

from .checks import CHECKS, run_check
from .target import CheckVerdict, ConformanceTarget

__all__ = ["CHECKS", "CheckVerdict", "ConformanceStudy", "ConformanceTarget", "QuantityTarget", "run_check"]
