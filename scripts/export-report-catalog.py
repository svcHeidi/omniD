#!/usr/bin/env python3
"""Export the active plugin's report catalog to JSON.

Backend authors report definitions against ``omnidriver/core/report_catalog.py``'s
``ReportDefinition`` record; each plugin owns its own catalog (the built-in
cardiac plugin's lives at ``omnidriver/cardiacfoam/reports.py``)
and this script writes it to a stable JSON catalog for external consumers.
``--plugin`` selects the plugin.

URL templates are emitted verbatim — substitution of ``{port}`` and
``{kind}`` happens outside this exporter. The Python side never knows the
runtime port, which keeps 4Dpapers swappable.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from omnidriver.core.report_catalog import to_record


def build_catalog(plugin: str) -> dict:
    from omnidriver.core.plugin_interface import load_plugin_context

    context = load_plugin_context(plugin)
    reports = context.capabilities.report_catalog.reports()
    return {
        "version": "1",
        "reports": [to_record(r) for r in reports],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True, help="output JSON path")
    parser.add_argument(
        "--plugin",
        required=True,
        help=(
            "Plugin whose report catalog to export: an installed plugin id, "
            "a trusted local-development import target "
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
