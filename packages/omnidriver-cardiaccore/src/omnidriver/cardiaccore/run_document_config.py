"""Construct the cardiacCore preprocessing RunDocument configuration."""

from __future__ import annotations

from pathlib import Path

from omnidriver.core.planning_types import diagnostic
from omnidriver.core.specs.validation import slot_key

from .input_overrides import read_input_values, validate_input_overrides


def build_config(spec):
    """Read the selected case, overlay requested x values, and retain evidence."""
    config = {"preprocessing": {}}
    try:
        values = read_input_values(Path(spec.case_root))
    except (FileNotFoundError, KeyError, ValueError, RuntimeError) as exc:
        return config, (
            diagnostic(
                "error",
                "unreadable_preprocessing_input",
                str(exc),
                source=str(spec.case_root),
            ),
        )

    requested = (spec.metadata or {}).get("input_overrides", {})
    try:
        values.update(validate_input_overrides(requested))
    except (TypeError, ValueError) as exc:
        return config, (diagnostic("error", "invalid_input_overrides", str(exc)),)

    config["preprocessing"] = {
        slot_key(driver_path): value for driver_path, value in values.items()
    }
    return config, ()
