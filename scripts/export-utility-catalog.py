#!/usr/bin/env python3
"""Export the active plugin's utility manifest catalog to JSON.

``--plugin`` selects the plugin; ``source_path`` is written relative to the utility root.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _manifest_to_record(manifest, root: Path) -> dict:
    """Serialise a ``UtilityManifest``, every field included, as a JSON-ready dict."""
    return {
        "name": manifest.name,
        "description": manifest.description,
        "purpose": manifest.purpose,
        "inputs": list(manifest.inputs),
        "requires_mesh": manifest.requires_mesh,
        "positional_args": [
            {
                "name": a.name,
                "argument_kind": a.argument_kind,
                "description": a.description,
            }
            for a in manifest.positional_args
        ],
        "flags": [
            {
                "name": f.name,
                "description": f.description,
                "takes_value": f.takes_value,
                "argument_kind": f.argument_kind,
                "required": f.required,
                "default": f.default,
            }
            for f in manifest.flags
        ],
        "produces": [
            {
                "artifact_id": pr.artifact_id,
                "path_pattern": pr.path_pattern,
                "format": pr.format,
                "description": pr.description,
                "produced_by": pr.produced_by,
                "variables": list(pr.variables),
                "optional": pr.optional,
                "instance_indexed": pr.instance_indexed,
            }
            for pr in manifest.produces
        ],
        "example": manifest.example,
        "category": manifest.category,
        "source_path": str(manifest.source_path.relative_to(root)),
    }


def build_catalog(plugin: str) -> dict:
    from omnidriver.core.plugin_interface import load_plugin_context

    context = load_plugin_context(plugin)

    manifests = context.stack.call("get_utility_manifests")
    # Relative to the directory every sidecar sits under, so no install path leaks.
    root = Path(os.path.commonpath([m.source_path.parent for m in manifests.values()])) if manifests else Path()
    return {
        "version": "1",
        "utilities": [
            _manifest_to_record(m, root)
            for m in sorted(manifests.values(), key=lambda m: m.name)
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True, help="output JSON path")
    parser.add_argument(
        "--plugin",
        required=True,
        help=(
            "Plugin whose utility catalog to export: an installed plugin id, "
            "a trusted local-development import target "
            "(module.path:PluginClass)."
        ),
    )
    args = parser.parse_args()
    catalog = build_catalog(args.plugin)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(catalog, indent=2, sort_keys=True))
    print(f"Wrote {len(catalog['utilities'])} utility entries to {out_path}")


if __name__ == "__main__":
    main()
