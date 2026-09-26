"""Results as comparable quantities (solver-neutral).

Design: docs/superpowers/specs/2026-09-26-results-as-quantities-design.md."""
from .comparison import (
    CHECKER_ID, CHECKER_VERSION, Tolerance, compare_pair, experiment_comparisons, overall_status,
    run_quantity_comparison,
)
from .errors import (
    PointReferenceError, QuantityComparisonError, QuantityError, QuantityReadError,
    ReaderDeclarationError, UnitError,
)
from .model import QUANTITY_STATUSES, ArtifactValueReader, Point, Quantity, RawSample, ReadRequest, not_evaluated
from .reading import check_reader, converted, read_quantities
from .reference import PointReference, ReferencePoint, load_point_reference, schema_errors
from .units import UNITS, check_convertible, convert, dimension_of

__all__ = [
    "ArtifactValueReader", "CHECKER_ID", "CHECKER_VERSION", "Point", "PointReference",
    "PointReferenceError", "QUANTITY_STATUSES", "Quantity", "QuantityComparisonError", "QuantityError",
    "QuantityReadError", "RawSample", "ReadRequest", "ReaderDeclarationError", "ReferencePoint",
    "Tolerance", "UNITS", "UnitError", "check_convertible", "check_reader", "compare_pair", "convert",
    "converted", "dimension_of", "experiment_comparisons", "load_point_reference", "not_evaluated",
    "overall_status", "read_quantities", "run_quantity_comparison", "schema_errors",
]
