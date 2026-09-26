"""Results as comparable quantities (solver-neutral).

Design: docs/superpowers/specs/2026-09-26-results-as-quantities-design.md."""
from .errors import (
    PointReferenceError, QuantityComparisonError, QuantityError, QuantityReadError,
    ReaderDeclarationError, UnitError,
)
from .model import QUANTITY_STATUSES, ArtifactValueReader, Point, Quantity, RawSample, ReadRequest, not_evaluated
from .reading import check_reader, converted, read_quantities
from .units import UNITS, check_convertible, convert, dimension_of

__all__ = [
    "ArtifactValueReader", "Point", "PointReferenceError", "QUANTITY_STATUSES", "Quantity",
    "QuantityComparisonError", "QuantityError", "QuantityReadError", "RawSample", "ReadRequest",
    "ReaderDeclarationError", "UNITS", "UnitError", "check_convertible", "check_reader", "convert",
    "converted", "dimension_of", "not_evaluated", "read_quantities",
]
