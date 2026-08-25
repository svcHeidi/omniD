from dataclasses import dataclass

from omnidriver.core.contracts.dictionary import Phase


@dataclass(frozen=True)
class ValidationError:
    phase: Phase
    field: str
    message: str
    level: str  # "error" | "warning"
