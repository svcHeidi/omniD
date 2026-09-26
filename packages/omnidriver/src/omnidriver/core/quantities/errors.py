"""Every refusal in the quantities package is a ValueError that names why."""
from __future__ import annotations


class QuantityError(ValueError):
    """Base class: a quantity, unit, reader, reference or comparison refused by name."""


class UnitError(QuantityError):
    """A unit is not in the table, or two units measure different things."""


class ReaderDeclarationError(QuantityError):
    """A reader's declaration (unit, sentinels, rule, coordinates) core cannot use."""


class QuantityReadError(QuantityError):
    """A read that does not answer the request it was given."""


class PointReferenceError(QuantityError):
    """A point-sampling reference file that is malformed or cites nothing."""


class QuantityComparisonError(QuantityError):
    """A comparison request refused before its report is written."""
