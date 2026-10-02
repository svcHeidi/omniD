"""cardiacFoam mutation hook for the legacy generic-case specification.

Core's generic-case factory addresses dictionary files through the neutral
``dict_file_relpaths``/``dict_file_overrides`` mappings. A generic case takes no
dictionary override: edits go through a tutorial record's study.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any


def apply_case_mutation(
    case_root: Path,
    *,
    dict_file_relpaths: Mapping[str, str | Path] | None = None,
    dict_file_overrides: Mapping[str, Any] | None = None,
) -> None:
    del case_root, dict_file_relpaths
    if any(dict_file_overrides or {}):
        raise ValueError(
            "a generic case folder takes no dictionary override; edit a case through a "
            "tutorial record's study (document:key patches)"
        )
