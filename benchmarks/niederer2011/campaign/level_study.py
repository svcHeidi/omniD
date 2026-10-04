#!/usr/bin/env python3
"""Write one level's study from a zip study, taking values only from it.

The campaign runs one sweep per level (one dx, or one dx and one time step)
so that each job asks for the ranks its mesh needs. This keeps the rows of
``--study`` whose values equal every ``--where``, in their order, and adds
each ``--set`` to ``base``. It changes no value the study states: a
``--set`` of a key the study already names is refused, and so is a
selection that keeps no row. Values are JSON (``dx=0.0005``, ``...=16``).

    python level_study.py --study <zip study> --cases-root <tutorials> --where dx=0.0005 --out <file>
    python level_study.py --study <zip study> --cases-root <tutorials> --where dx=0.0001 \\
        --where system/controlDict:deltaT=5e-05 \\
        --set system/decomposeParDict:numberOfSubdomains=16 --out <file>

A relative ``cases_root`` is read against the root of the ``--repo`` repository,
and the campaign runs with ``--plugin`` and no repository, so ``--cases-root``
(where the tutorials are on this machine) is written into the level study as an
absolute path. It is a place, not a study value.

Case ids follow the kept rows' order (case_0001, case_0002, ...); the
campaign's requests name them (README, "Levels and case ids").
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _assignment(text: str) -> tuple[str, object]:
    key, sep, value = text.partition("=")
    if not sep or not key:
        raise argparse.ArgumentTypeError(f"expected KEY=VALUE, got {text!r}")
    try:
        return key, json.loads(value)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(f"{text!r}: the value is not JSON ({exc})") from None


def level_study(
    study: dict, where: list[tuple[str, object]], sets: list[tuple[str, object]], cases_root: Path,
) -> dict:
    sweep = study.get("sweep", {})
    if sweep.get("mode") != "zip" or sweep.get("dependent"):
        raise ValueError("only a zip study with no 'dependent' entries can be sliced by row")
    independent = sweep["independent"]
    for key, _ in where:
        if key not in independent:
            raise ValueError(f"--where {key!r}: the study sweeps {sorted(independent)}")
    rows = [i for i in range(len(next(iter(independent.values()))))
            if all(independent[key][i] == value for key, value in where)]
    if not rows:
        raise ValueError(f"no row of the study has {dict(where)}")
    base = {**study.get("base", {}), "cases_root": str(cases_root.resolve())}
    for key, value in sets:
        if key in base or key in independent:
            raise ValueError(f"--set {key!r}: the study already states it; a level study adds, never overrides")
        base[key] = value
    return {"base": base, "sweep": {"mode": "zip",
                                    "independent": {key: [values[i] for i in rows] for key, values in independent.items()}}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--study", type=Path, required=True)
    parser.add_argument("--cases-root", type=Path, required=True)
    parser.add_argument("--where", type=_assignment, action="append", default=[], required=True)
    parser.add_argument("--set", dest="sets", type=_assignment, action="append", default=[])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        level = level_study(json.loads(args.study.read_text()), args.where, args.sets, args.cases_root)
    except (OSError, ValueError, KeyError) as exc:
        print(f"level_study: {exc}", file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(level, indent=2) + "\n")
    print(f"{args.out}: {len(next(iter(level['sweep']['independent'].values())))} case(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
