from dataclasses import dataclass


@dataclass(frozen=True)
class ValidationError:
    phase: str          # a plugin-declared phase, not core's Phase literal
    field: str
    message: str
    level: str  # "error" | "warning"
