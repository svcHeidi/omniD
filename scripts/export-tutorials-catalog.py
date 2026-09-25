#!/usr/bin/env python3
#----------------------------------------------------------------------------#
# License
#     This file is part of cardiacFoam.
#
#     cardiacFoam is free software: you can redistribute it and/or modify it
#     under the terms of the GNU General Public License as published by the
#     Free Software Foundation, either version 3 of the License, or (at your
#     option) any later version.
#
#     cardiacFoam is distributed in the hope that it will be useful, but
#     WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#     General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with cardiacFoam.  If not, see <http://www.gnu.org/licenses/>.
#
# Script
#     export-tutorials-catalog
#
# Description
#     Exports tutorial metadata definitions to JSON format.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

"""Export the tutorial catalog.

Cross-checks the default plugin's ``get_tutorial_displays()`` against
``core.runtime.registry.list_tutorials()`` so we cannot ship a tutorial
catalog entry without a backend factory, or omit a registered tutorial.
Writes a stable JSON shape to the requested output path.

Source-of-truth stays in Python (the user confirmed: "the tutorials are
currently running based on hardcoded scripts in the backend. that is okay").
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from omnidriver.core.runtime.registry import list_tutorials
from omnidriver.core.plugin_interface import (
    default_driver_context,
    load_plugin_context,
)
from omnidriver.core.tutorials_display import to_record


def build_catalog(plugin: str | None = None) -> dict:
    # `selected` rather than reusing `plugin`: the argument is a plugin *id*
    # and this is the plugin *object*. Binding both to one name reads as a
    # mistake even when it is not.
    context = load_plugin_context(plugin) if plugin else default_driver_context()
    # `.plugin` was the retired single-plugin field (Task 7's
    # `DriverContext` now holds an ordered `.providers` stack); the most
    # specific provider -- last in the ordered tuple -- is this selection.
    selected = context.providers[-1]
    display_ids = {t.id for t in selected.get_tutorial_displays()}
    registry_ids = set(list_tutorials(context))
    # A tutorial's backend is EITHER a factory (`registry_ids`, above) OR a
    # tutorial record (design doc docs/superpowers/specs/2026-09-24-
    # tutorials-are-pointers-design.md) -- `restitutionCurves` (step 4b, the
    # pilot) is the first display row backed by a record rather than a
    # factory. `list_tutorials()` deliberately only ever names factories
    # (`registry.py`'s own `list_tutorials` docstring/callers), so this
    # exporter -- not core -- treats the union as "has a real backend",
    # since it is the one place that already knows both catalogs need
    # checking here.
    record_ids = set((context.capabilities.tutorial_records.catalog() or {}).keys())
    known_backend_ids = registry_ids | record_ids

    only_in_display = display_ids - known_backend_ids
    only_in_backend = known_backend_ids - display_ids
    if only_in_display or only_in_backend:
        raise SystemExit(
            "default plugin get_tutorial_displays() is out of sync with "
            "list_tutorials()/tutorial_records. "
            f"only-in-display={sorted(only_in_display)} "
            f"only-in-backend={sorted(only_in_backend)}. "
            "Either add a TutorialDisplay row or remove it; both "
            "sets must match exactly."
        )

    # Stable order: keep list_tutorials()' declared factory order first
    # (unchanged from before tutorial records existed), then any
    # record-backed ids not already a factory, sorted -- reproducible
    # regardless of get_tutorial_displays()'s or the record catalog's own
    # dict order.
    by_id = {t.id: t for t in selected.get_tutorial_displays()}
    ordered_ids = list(list_tutorials(context)) + sorted(record_ids - registry_ids)
    return {
        "version": "1",
        "tutorials": [to_record(by_id[name]) for name in ordered_ids],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True, help="output JSON path")
    parser.add_argument(
        "--plugin",
        help=(
            "Plugin whose tutorial catalog to export: an installed plugin id, "
            "a trusted local-development import target "
            "(module.path:PluginClass). Defaults to the single installed adapter."
        ),
    )
    args = parser.parse_args()
    catalog = build_catalog(args.plugin)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(catalog, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
