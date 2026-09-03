from dataclasses import dataclass


@dataclass(frozen=True)
class ValidationError:
    phase: str          # a plugin-declared phase; core declares none
    field: str
    message: str
    level: str  # "error" | "warning"
