#!/usr/bin/env python3
"""Verify a *built and installed* omnidriver wheel actually works.

Run with the interpreter of a venv that has the wheel installed -- not an
editable install, and not this repository on ``sys.path``:

    python -m build --outdir dist packages/omnidriver
    python -m venv /tmp/wheelenv
    /tmp/wheelenv/bin/pip install "dist/omnidriver-*.whl[post]"
    /tmp/wheelenv/bin/python scripts/check-wheel-artifact.py

Why this is not covered by the test suite: an editable install leaves the
repository on the path, so a module that reads repo-relative state at import
time still works and the defect stays invisible.

Deliberately does NOT run the core pytest suite. Eight of its modules call
``repo_root_default()`` at import time and so error during collection outside a
checkout; they test repository tooling (documentation contracts, the CLI),
not the shipped library. Running them here would fail
for the wrong reason. Making them skip cleanly is worth doing separately.
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

    # 3. The CLI is reachable. It hard-imported omnidriver.openfoam at module
    #    scope once, which made the whole command surface unusable in a
    #    core-only install.
    result = subprocess.run(
        [sys.executable, "-m", "omnidriver", "--help"], capture_output=True, text=True
    )
    print(f"`python -m omnidriver --help`: exit {result.returncode}")
    if result.returncode != 0:
        failures.append(f"CLI --help exited {result.returncode}: {result.stderr[:300]}")

    # 4. The sweep-spec schema ships inside the installed package -- a
    #    repository-only schemas/ file would pass every other
    #    check here and still be absent from every wheel, which is exactly
    #    the defect class this script exists to catch.
    try:
        import importlib.resources as _resources
        import json as _json

        payload = (
            _resources.files("omnidriver.schemas")
            .joinpath("sweep-spec.schema.json")
            .read_text()
        )
        schema = _json.loads(payload)
        schema_id = schema.get("$id", "")
        if not schema_id.rsplit("/", 1)[-1].startswith("v"):
            failures.append(
                f"sweep-spec.schema.json $id {schema_id!r} does not end in a version"
            )
        else:
            print(f"sweep-spec schema present   : $id={schema_id}")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"sweep-spec.schema.json unreadable from the wheel: {exc}")

    if failures:
        print("\nFAILED:")
        for f in failures:
            print(f"  {f}")
        return 1
    print("\nWheel artifact OK: core installs and runs standalone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
