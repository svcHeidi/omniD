#!/usr/bin/env python3
"""Verify a built and installed omnidriver wheel works.

Run it with the interpreter of a venv holding the wheel, not an editable install.
"""
from __future__ import annotations

import importlib
import pkgutil
import subprocess
import sys

SIBLING_PACKAGES = (".cardiacfoam", ".openfoam")


def main() -> int:
    import omnidriver

    failures: list[str] = []

    # 1. Every core module imports with nothing but the wheel installed.
    names = [
        m.name
        for m in pkgutil.walk_packages(omnidriver.__path__, "omnidriver.")
        if not any(sib in m.name for sib in SIBLING_PACKAGES)
    ]
    if not names:
        print("FAIL: walked zero modules -- the wheel is not installed here")
        return 1
    for name in names:
        try:
            importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001 -- report, do not mask
            failures.append(f"import {name}: {type(exc).__name__}: {exc}")
    print(f"modules imported            : {len(names) - len(failures)}/{len(names)}")

    # 2. With no plugin distribution installed, the CLI refuses to run a
    #    record without one named: core has no built-in solver context.
    result = subprocess.run(
        [sys.executable, "-m", "omnidriver", "describe", "--entry", "x"],
        capture_output=True, text=True,
    )
    print(f"describe with no plugin     : exit {result.returncode}")
    if result.returncode != 2 or "no plugin was selected" not in result.stderr:
        failures.append(
            f"`describe` with no plugin exited {result.returncode}, not the named refusal: {result.stderr[:300]}"
        )

    # 3. The CLI is reachable in a core-only install.
    result = subprocess.run(
        [sys.executable, "-m", "omnidriver", "--help"], capture_output=True, text=True
    )
    print(f"`python -m omnidriver --help`: exit {result.returncode}")
    if result.returncode != 0:
        failures.append(f"CLI --help exited {result.returncode}: {result.stderr[:300]}")

    # 4. The run-document schema ships inside the installed package; a
    #    repository-only schemas/ file would pass every other check here.
    try:
        import importlib.resources as _resources
        import json as _json

        schema = _json.loads(
            _resources.files("omnidriver.schemas").joinpath("run-document.json").read_text()
        )
        print(f"run-document schema present : {schema['title']}")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"run-document.json unreadable from the wheel: {exc}")

    if failures:
        print("\nFAILED:")
        for f in failures:
            print(f"  {f}")
        return 1
    print("\nWheel artifact OK: core installs and runs standalone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
