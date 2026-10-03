"""``omnidriver build``: author a runnable case from a solver's catalogue when there is no native case; a native case stays the default.

The solver package declares its builder under the ``omnidriver.builders`` entry-point group, named like its plugin."""

from __future__ import annotations

import argparse
import json
from importlib.metadata import entry_points
from pathlib import Path

BUILDERS_GROUP = "omnidriver.builders"


def _pairs(parser: argparse.ArgumentParser, flag: str, values: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for raw in values:
        name, separator, value = raw.partition("=")
        if not separator or not name or name in parsed:
            parser.error(f"{flag} {raw!r} must be NAME=VALUE, each NAME once")
        parsed[name] = value
    return parsed


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="omnidriver build",
        description=(
            "Build a case from the catalogue into --out and hold it to the same pre-run rules a "
            "record's case passes. Run it with `omnidriver run --strict --case <out>`."
        ),
    )
    parser.add_argument("--plugin", required=True, help="An installed plugin id whose package declares a case builder.")
    parser.add_argument("--out", required=True, metavar="DIR", help="The case directory to write.")
    parser.add_argument("--select", action="append", default=[], metavar="NAME=VALUE",
                        help="A discriminator the catalogue branches on, such as myocardiumSolver=singleCellSolver.")
    parser.add_argument("--set", action="append", default=[], metavar="PATH=VALUE", dest="set_values",
                        help="A catalogue key to set, by its driver path.")
    parser.add_argument("--option", action="append", default=[], metavar="NAME=VALUE",
                        help="A solver-specific build option, such as dx or endTime.")
    parser.add_argument("--overwrite", action="store_true", help="Replace the dictionaries of an existing case.")
    args = parser.parse_args(argv)

    declared = {entry.name: entry for entry in entry_points(group=BUILDERS_GROUP)}
    if args.plugin not in declared:
        parser.error(f"plugin {args.plugin!r} declares no case builder; installed: {sorted(declared) or 'none'}")
    from .plugin_interface import load_plugin_context

    try:
        result = declared[args.plugin].load()(
            load_plugin_context(args.plugin), Path(args.out).expanduser().resolve(),
            select=_pairs(parser, "--select", args.select), set_values=_pairs(parser, "--set", args.set_values),
            options=_pairs(parser, "--option", args.option), overwrite=args.overwrite,
        )
    except (ValueError, OSError) as exc:
        result = {"status": "failed", "error": str(exc)}
    print(json.dumps({"action": "build", "plugin": args.plugin, **result}, indent=2))
    return 0 if result["status"] == "ok" else 1
