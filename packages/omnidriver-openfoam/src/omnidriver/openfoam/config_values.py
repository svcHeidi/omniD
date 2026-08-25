from __future__ import annotations

from pathlib import Path

from .mutators import read_foam_entry


def openfoam_config_value_reader():
    def _read(path: Path, key: str) -> str | None:
        return read_foam_entry(path, key)

    return _read
