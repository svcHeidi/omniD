#!/usr/bin/env python3
"""Export ``dict_entries`` and the ionic / active-tension catalogs to JSON.

The exporter reads ``DictEntry`` objects and fans each one out into one record
per phase the entry declares. An entry tagged ``phases={"anatomy", "physics"}``
therefore appears in BOTH the ``anatomy`` and ``physics`` buckets; each emitted
record carries a single ``phase`` field equal to its bucket and preserves the
full ``phases`` list for validation and agent consumers.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from omnidriver.cardiacfoam.dict_entries import get_electro_property_entry_groups
from omnidriver.cardiacfoam.common_dict_entries import PHYSICS_PROPERTY_ENTRIES
from omnidriver.cardiacfoam.ionic_model_catalog import IONIC_MODEL_CATALOG
from omnidriver.cardiacfoam.active_tension_catalog import (
    ACTIVE_TENSION_MODEL_CATALOG,
)

PHASES = ("anatomy", "physics", "stimulus", "solver")


def _all_entries(context):
    """Yield every ``DictEntry`` known to the backend, regardless of group."""
    entries: list[DictEntry] = list(PHYSICS_PROPERTY_ENTRIES)
    for group in get_electro_property_entry_groups(context).values():
        entries.extend(group)
    yield from entries


def _entry_to_record(e) -> dict:
    """Flatten a ``DictEntry`` to a JSON record.

    ``phases`` arrives as a ``frozenset`` (unordered, not JSON-serialisable);
    we emit a sorted list so the catalog JSON is stable across runs.
    """
    d = asdict(e)
    d["phases"] = sorted(e.phases)
    return d


def build_catalog(plugin: str) -> dict:
    from omnidriver.core.plugin_interface import load_plugin_context

    context = load_plugin_context(plugin)

    by_phase: dict[str, list] = {p: [] for p in PHASES}
    for e in _all_entries(context):
        if not e.phases:
            raise SystemExit(f"entry missing phases: {e.driver_path}")
        record = _entry_to_record(e)
        # Fan-out: one record per declared phase. Each emitted record is
        # stamped with a single `phase` (its bucket) while keeping `phases`
        # so downstream consumers know the entry's other homes.
        for ph in e.phases:
            if ph not in by_phase:
                raise SystemExit(
                    f"entry {e.driver_path} has unknown phase {ph!r}"
                )
            by_phase[ph].append({**record, "phase": ph})
    return {
        "version": "1",
        "phases": {p: {"entries": by_phase[p]} for p in PHASES},
        "ionic_models": [asdict(m) for m in IONIC_MODEL_CATALOG.values()],
        "active_tension_models": [
            asdict(m) for m in ACTIVE_TENSION_MODEL_CATALOG.values()
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True, help="output JSON path")
    parser.add_argument(
        "--plugin",
        required=True,
        help=(
            "Plugin whose dictionary entries to export: an installed plugin id, "
            "or a trusted local-development import target "
            "(module.path:PluginClass)."
        ),
    )
    args = parser.parse_args()
    catalog = build_catalog(args.plugin)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(catalog, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
